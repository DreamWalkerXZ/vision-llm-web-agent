"""
File Operations Tools
Tools for downloading, processing, and managing files
"""

from pathlib import Path
from typing import Optional

import pymupdf  # PyMuPDF
from PIL import Image

from .base import tool
from .browser_control import browser_state
from ..config.settings import ARTIFACTS_DIR, get_session_artifacts_dir
import pytesseract


# file_operations.py (Updated)

def normalize_file_path(file_path: str, is_input: bool = False) -> Path:
    """
    Normalize file path to be relative to the current session artifacts directory, supporting nesting.
    Uses session-specific directory if available, otherwise falls back to ARTIFACTS_DIR.
    Handles both Windows and Unix path separators.
    """
    # Normalize path separators: convert backslashes to forward slashes first
    # Path() will handle the rest correctly for the current OS
    normalized_path = file_path.replace("\\", "/") if "\\" in file_path else file_path
    path_obj = Path(normalized_path)
    
    # Get the current session artifacts directory (or fallback to ARTIFACTS_DIR)
    session_artifacts_dir = get_session_artifacts_dir()

    # 1. If path is absolute, use it directly (e.g., used by temp pytest fixtures)
    if path_obj.is_absolute():
        return path_obj
    
    # 2. If path is already rooted at ARTIFACTS_DIR or session directory, use it
    if path_obj.parts[0] == ARTIFACTS_DIR.name or path_obj.parts[0] == session_artifacts_dir.name:
        # e.g., 'artifacts/test/file.pdf' or '20251122_123456/test/file.pdf'
        return path_obj
    
    # 3. Otherwise, treat it as a path relative to session artifacts directory (supports 'test/file.pdf')
    # This is the key change to support nested paths and session-specific directories
    full_path = session_artifacts_dir / path_obj
    
    # For input files, handle existence checks
    if is_input:
        # Try full_path (artifacts/test/file.pdf)
        if full_path.exists():
            return full_path
        # Fallback 1: Try absolute paths from temp fixtures (already handled by path_obj.is_absolute())
        # Fallback 2: Try original path relative to CWD if it exists (less common, but safe)
        if path_obj.exists():
            return path_obj
        # If nothing exists, return the expected full path so the exception can be raised properly
        return full_path
    
    # For output files, always return the full, nested path relative to ARTIFACTS_DIR
    return full_path

# Update all tool functions to use the returned Path object directly
# For example, in write_text_to_file:
#    file_path_obj = normalize_file_path(file_name, is_input=False)
#    file_path_obj.parent.mkdir(parents=True, exist_ok=True)
#    with open(file_path_obj, "w", encoding="utf-8") as f:
#        f.write(content)


@tool(
    name="download_pdf",
    description="Download a PDF file from URL. Provide only the filename (e.g., 'abc.pdf'), not directory path. If url is 'current' or empty, downloads from current page URL.",
    parameters={
        "url": "string (required, use 'current' to download from current page)",
        "file_name": "string (required, filename only, e.g., 'abc.pdf')"
    },
    category="file_operations"
)
def download_pdf_file(url: str, file_name: str) -> str:
    """Download a PDF file from a URL or current page"""
    browser_state.initialize()
    
    try:
        # If url is 'current' or empty, use current page URL
        if not url or url.lower() == 'current':
            if not browser_state.is_initialized:
                return "❌ Browser not initialized. Call goto() first or provide a URL."
            url = browser_state.page.url
            print(f"   📄 Using current page URL: {url}")
        
        # Normalize path to artifacts/filename (single level)
        save_path = normalize_file_path(file_name, is_input=False)
        
        # Ensure parent directory exists
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Strategy 1: Use API request to fetch PDF directly (works best for direct PDF URLs)
        try:
            response = browser_state.context.request.get(url, timeout=30000)
            if response.ok:
                pdf_content = response.body()
                
                # Verify it's actually a PDF
                if pdf_content.startswith(b'%PDF'):
                    with open(save_path, 'wb') as f:
                        f.write(pdf_content)
                    
                    size = Path(save_path).stat().st_size
                    # Use forward slashes in path display for better readability across platforms
                    display_path = str(save_path).replace("\\", "/")
                    return f"✅ PDF downloaded to: {display_path} (size: {size} bytes)"
                else:
                    # Not a PDF, try other strategies
                    print(f"   ⚠️  Response doesn't appear to be a PDF (first bytes: {pdf_content[:20]})")
        except Exception as e:
            # Fall back to page navigation methods
            print(f"   ⚠️  Strategy 1 (API request) failed: {str(e)}")
        
        # Strategy 2: Try download event (for file download links)
        download_page = None
        try:
            download_page = browser_state.context.new_page()
            with download_page.expect_download(timeout=10000) as download_info:
                download_page.goto(url, timeout=15000, wait_until="networkidle")
                download = download_info.value
                download.save_as(save_path)
                
                if Path(save_path).exists():
                    size = Path(save_path).stat().st_size
                    if size > 0:
                        # Verify it's a PDF
                        with open(save_path, 'rb') as f:
                            first_bytes = f.read(4)
                        if first_bytes == b'%PDF':
                            if download_page:
                                download_page.close()
                            display_path = str(save_path).replace("\\", "/")
                            return f"✅ PDF downloaded to: {display_path} (size: {size} bytes)"
                        else:
                            # Not a PDF, delete the file
                            Path(save_path).unlink()
                            print(f"   ⚠️  Downloaded file is not a PDF")
        except Exception as e:
            # If download event didn't trigger, try next strategy
            print(f"   ⚠️  Strategy 2 (download event) failed: {str(e)}")
        finally:
            if download_page:
                download_page.close()
        
        # Strategy 3: Try to get PDF content from current page if we're on a PDF page
        try:
            if browser_state.is_initialized and browser_state.page.url == url:
                # Try to get PDF content via JavaScript
                pdf_content = browser_state.page.evaluate("""() => {
                    try {
                        // Try to get PDF content from embedded viewer or iframe
                        const iframe = document.querySelector('iframe[src*=".pdf"], embed[src*=".pdf"], object[data*=".pdf"]');
                        if (iframe) {
                            return iframe.src || iframe.getAttribute('data') || iframe.getAttribute('src');
                        }
                        return null;
                    } catch(e) {
                        return null;
                    }
                }""")
                
                if pdf_content and pdf_content != url:
                    # Recursively try to download from the iframe URL
                    return download_pdf_file(pdf_content, file_name)
        except Exception as e:
            print(f"   ⚠️  Strategy 3 (iframe detection) failed: {str(e)}")
        
        # Strategy 4: Try using requests library as fallback (if available)
        try:
            import requests
            response = requests.get(url, timeout=30, stream=True)
            if response.status_code == 200:
                content = response.content
                if content.startswith(b'%PDF'):
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    size = Path(save_path).stat().st_size
                    # Use forward slashes in path display for better readability across platforms
                    display_path = str(save_path).replace("\\", "/")
                    return f"✅ PDF downloaded to: {display_path} (size: {size} bytes)"
        except ImportError:
            pass  # requests not available
        except Exception as e:
            print(f"   ⚠️  Strategy 4 (requests library) failed: {str(e)}")
        
        return f"❌ Failed to download PDF from {url}. Tried multiple strategies but none succeeded. Please check if the URL is accessible and points to a valid PDF file."
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f"❌ Failed to download PDF: {str(e)}\n   Details: {error_details[:200]}"


@tool(
    name="pdf_extract_text",
    description="Extract text from PDF file. Provide only the filename (e.g., 'abc.pdf'), not directory path. If searching for specific content (e.g., 'Figure 1'), omit page_num to search all pages. The tool will automatically highlight pages containing 'Figure' references.",
    parameters={
        "file_name": "string (required, filename only, e.g., 'abc.pdf')",
        "page_num": "int (optional, specific page number, 0-indexed. Omit to extract from all pages)",
        "search_term": "string (optional, search for specific term like 'Figure 1' and return only relevant pages)"
    },
    category="file_operations"
)
def extract_pdf_text(file_name: str, page_num: Optional[int] = None, search_term: Optional[str] = None) -> str:
    """Extract text from a PDF file, with optional search functionality"""
    try:
        # Normalize path to artifacts/filename (single level)
        pdf_path = normalize_file_path(file_name, is_input=True)
        
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        
        if page_num is not None:
            # Convert 1-based to 0-based if needed (handle both conventions)
            if page_num > 0:
                page_idx = page_num - 1  # Assume 1-based input
            else:
                page_idx = page_num  # 0-based input
            
            if page_idx < 0 or page_idx >= total_pages:
                doc.close()
                return f"❌ Page {page_num} does not exist. PDF has {total_pages} pages (use 1-{total_pages} or 0-{total_pages-1})."
            page = doc[page_idx]
            text = page.get_text()
            doc.close()
            return f"Page {page_num} (of {total_pages} total):\n{text}"
        else:
            # Extract from all pages with page numbers clearly marked
            import re
            
            # If search_term is provided, only return pages containing the search term
            if search_term:
                matching_pages = []
                for i, page in enumerate(doc):
                    page_text = page.get_text()
                    if search_term.lower() in page_text.lower():
                        matching_pages.append((i, page_text))
                
                if not matching_pages:
                    doc.close()
                    return f"❌ Search term '{search_term}' not found in PDF (Total pages: {total_pages})"
                
                text = f"📄 Search Results for '{search_term}' (Found in {len(matching_pages)} page(s) out of {total_pages} total):\n"
                text += f"{'='*80}\n"
                for i, page_text in matching_pages:
                    text += f"\n{'='*80}\nPage {i+1} (0-indexed: {i}):\n{'='*80}\n"
                    # Highlight the search term in context (show surrounding text)
                    lines = page_text.split('\n')
                    for line in lines:
                        if search_term.lower() in line.lower():
                            text += f"🔍 {line}\n"
                        else:
                            text += f"{line}\n"
                    # Find all figure references on this page
                    figure_matches = re.findall(r'Figure\s+(\d+)', page_text, re.IGNORECASE)
                    if figure_matches:
                        text += f"\n💡 This page contains Figure(s): {', '.join(sorted(set(figure_matches), key=lambda x: int(x)))}\n"
                doc.close()
                return text
            else:
                # Extract from all pages with page numbers clearly marked
                import re
                
                text = f"📄 PDF Text Content (Total pages: {total_pages})\n"
                text += f"{'='*80}\n"
                text += f"💡 TIP: If searching for 'Figure 1', use search_term='Figure 1' parameter to find it faster!\n"
                text += f"{'='*80}\n"
                
                # First pass: find all pages with Figure references
                figure_pages = {}  # {page_num: [figure_numbers]}
                for i, page in enumerate(doc):
                    page_text = page.get_text()
                    if "Figure" in page_text or "figure" in page_text.lower():
                        figure_matches = re.findall(r'Figure\s+(\d+)', page_text, re.IGNORECASE)
                        if figure_matches:
                            figure_pages[i+1] = sorted(set(figure_matches), key=lambda x: int(x))
                
                # Add summary of Figure locations at the top
                if figure_pages:
                    text += f"\n📊 FIGURE LOCATIONS SUMMARY:\n"
                    for page_num, figures in sorted(figure_pages.items()):
                        text += f"   Page {page_num}: Figure(s) {', '.join(figures)}\n"
                    text += f"\n{'='*80}\n"
                
                # Add guidance for summarization tasks
                # Check if this is likely a summarization task by checking recent history
                # This will be added at the end of the text extraction
                summarization_hint = "\n\n💡 NEXT STEPS FOR SUMMARIZATION:\n"
                summarization_hint += "If your task is to summarize this paper, you should:\n"
                summarization_hint += "1. Review the extracted text above (especially Abstract, Introduction, and Conclusion sections)\n"
                summarization_hint += "2. Use write_text tool to create a summary file (e.g., write_text(file_name=\"summary.txt\", content=\"your summary here\"))\n"
                summarization_hint += "3. The summary should cover: main contributions, methodology, key results, and conclusions\n"
                summarization_hint += "4. After writing the summary, mark the task as complete\n"
                
                # Extract text from all pages (limit to first 5000 chars per page to avoid overwhelming)
                MAX_CHARS_PER_PAGE = 5000
                for i, page in enumerate(doc):
                    page_text = page.get_text()
                    if len(page_text) > MAX_CHARS_PER_PAGE:
                        page_text = page_text[:MAX_CHARS_PER_PAGE] + f"\n... (truncated, {len(page.get_text()) - MAX_CHARS_PER_PAGE} more characters)"
                    
                    text += f"\n{'='*80}\nPage {i+1} (0-indexed: {i}):\n{'='*80}\n"
                    text += page_text
                    
                    # Add a hint if "Figure" is mentioned on this page
                    if i+1 in figure_pages:
                        text += f"\n💡 NOTE: This page contains Figure(s): {', '.join(figure_pages[i+1])}\n"
                
                # Add summarization guidance at the end
                text += summarization_hint
                
                doc.close()
                return text
    
    except Exception as e:
        return f"❌ Failed to extract text from PDF: {str(e)}"


@tool(
    name="pdf_extract_images",
    description="Extract images from PDF file. Provide only filenames (e.g., 'abc.pdf'), not directory paths.",
    parameters={
        "file_name": "string (required, filename only, e.g., 'abc.pdf')",
        "output_dir": "string (required, directory name only, e.g., 'images')",
        "page_num": "int (optional, specific page)"
    },
    category="file_operations"
)
def extract_pdf_images(file_name: str, output_dir: str, page_num: Optional[int] = None) -> str:
    """Extract images from a PDF file"""
    try:
        # 1. 规范化 PDF 输入文件路径 (假设它返回 Path 对象)
        pdf_path_obj = normalize_file_path(file_name, is_input=True)
        
        # 2. 🚨 关键修复：使用 normalize_file_path 规范化输出目录路径。
        #    这将支持 'test/extracted_images' 这样的嵌套路径。
        output_dir_path = normalize_file_path(output_dir, is_input=False)
        
        # 3. 确保目标输出目录存在
        #    因为 output_dir 已经是最终的目录路径 (如 artifacts/test/extracted_images)，
        #    我们直接创建它，包括所有父目录。
        output_dir_path.mkdir(parents=True, exist_ok=True)
        
        # 检查 PDF 文件是否存在 (使用规范化后的 Path 对象)
        if not pdf_path_obj.exists():
             display_path = str(pdf_path_obj).replace("\\", "/")
             return f"❌ PDF file not found at: {display_path}"
        
        doc = pymupdf.open(pdf_path_obj) # 使用 Path 对象
        total_pages = len(doc)
        saved_images = []
        
        pages_to_process = [page_num] if page_num is not None else range(total_pages)
        
        for page_idx in pages_to_process:
            if page_idx >= total_pages:
                continue
                
            page = doc[page_idx]
            image_list = page.get_images()
            
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                image_filename = f"page_{page_idx+1}_img_{img_idx+1}.{image_ext}"
                # 4. 关键修复：将图片保存到正确的、支持嵌套的目录 Path 对象中
                image_path = output_dir_path / image_filename
                
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                saved_images.append(str(image_path))
        
        doc.close()
        
        if saved_images:
            # 5. 返回信息包含相对路径（相对于session artifacts目录），方便VLLM使用
            from ..config.settings import get_session_artifacts_dir
            session_artifacts_dir = get_session_artifacts_dir()
            relative_paths = []
            for img_path in saved_images:
                try:
                    # 计算相对于session artifacts目录的相对路径
                    rel_path = Path(img_path).relative_to(session_artifacts_dir)
                    # 统一使用正斜杠，避免Windows反斜杠问题
                    rel_path_str = str(rel_path).replace("\\", "/")
                    relative_paths.append(rel_path_str)
                except ValueError:
                    # 如果不在session目录下，使用完整路径，但统一为正斜杠
                    rel_path_str = str(img_path).replace("\\", "/")
                    relative_paths.append(rel_path_str)
            
            result_msg = f"✅ Extracted {len(saved_images)} images to {output_dir}:\n"
            result_msg += "\n".join([f"  - {rel_path}" for rel_path in relative_paths])
            result_msg += f"\n💡 To use OCR, provide the relative path (e.g., '{relative_paths[0] if relative_paths else 'extracted_images/page_X_img_Y.png'}')"
            if page_num is not None:
                result_msg += f"\n💡 Note: Only extracted from page {page_num + 1}. PDF has {total_pages} pages total. If you need more images, try extracting from other pages or omit page_num to extract from all pages."
            return result_msg
        else:
            # Provide helpful guidance when no images found
            if page_num is not None:
                return f"⚠️ No images found on page {page_num + 1} of the PDF. The PDF has {total_pages} pages total. Try extracting from other pages (e.g., page_num=2, page_num=3) or omit page_num parameter to extract from all pages."
            else:
                return f"⚠️ No images found in the PDF (searched all {total_pages} pages)."
    
    except Exception as e:
        return f"❌ Failed to extract images from PDF: {str(e)}"


@tool(
    name="save_image",
    description="Save, copy, or crop an image. Can copy images from subdirectories (e.g., 'extracted_images/page_1_img_1.png') to main artifacts directory. Provide relative paths for input (e.g., 'extracted_images/page_1_img_1.png') and filename only for output (e.g., 'figure1.png').",
    parameters={
        "file_name": "string (required, relative path from artifacts/ or filename, e.g., 'extracted_images/page_1_img_1.png' or 'image.png')",
        "output_file_name": "string (optional, filename only, e.g., 'figure1.png' or 'cropped.png')",
        "crop_box": "list (optional, [left, top, right, bottom])"
    },
    category="file_operations"
)
def save_or_crop_image(file_name: str, output_file_name: Optional[str] = None, 
                       crop_box: Optional[list] = None) -> str:
    """
    Save, copy, or crop an image. 
    Supports copying images from subdirectories (e.g., extracted_images/) to main artifacts directory.
    """
    try:
        # Normalize input image path - supports both relative paths and filenames
        # Handle Windows backslash paths by converting to forward slashes first
        normalized_file_name = file_name.replace("\\", "/") if "\\" in file_name else file_name
        
        # First try as relative path (e.g., 'extracted_images/page_1_img_1.png')
        image_path = normalize_file_path(normalized_file_name, is_input=True)
        
        # If not found, try searching in common subdirectories
        if not image_path.exists():
            from ..config.settings import get_session_artifacts_dir
            session_artifacts_dir = get_session_artifacts_dir()
            filename_only = Path(normalized_file_name).name
            # Try common subdirectories
            common_dirs = ["extracted_images", "images", "output_images"]
            for subdir in common_dirs:
                potential_path = session_artifacts_dir / subdir / filename_only
                if potential_path.exists():
                    image_path = potential_path
                    break
            else:
                # Still not found, return error
                return f"❌ Image not found: {file_name}. Searched in: {normalized_file_name}, and subdirectories: {', '.join(common_dirs)}"
        
        img = Image.open(image_path)
        
        if crop_box:
            if len(crop_box) != 4:
                return "❌ crop_box must be [left, top, right, bottom]"
            img = img.crop(tuple(crop_box))
        
        # Normalize output path to artifacts/filename (single level)
        if output_file_name:
            save_path = normalize_file_path(output_file_name, is_input=False)
        else:
            # Use same filename as input (extract just the filename)
            save_path = normalize_file_path(Path(image_path).name, is_input=False)
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        img.save(save_path)
        # Use forward slashes in path display for better readability
        display_path = str(save_path).replace("\\", "/")
        return f"✅ Image saved to: {display_path}"
    
    except Exception as e:
        return f"❌ Failed to save image: {str(e)}"


@tool(
    name="write_text",
    description="Write text content to a file. Provide only the filename (e.g., 'output.txt'), not directory path.",
    parameters={
        "content": "string (required)",
        "file_name": "string (required, filename only, e.g., 'output.txt')"
    },
    category="file_operations"
)
def write_text_to_file(content: str, file_name: str) -> str:
    """Write text content to a file"""
    try:
        # Normalize path to artifacts/filename (single level)
        file_path = normalize_file_path(file_name, is_input=False)
        
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Use forward slashes in path display for better readability
        display_path = str(file_path).replace("\\", "/")
        return f"✅ Text written to: {display_path}"
    
    except Exception as e:
        return f"❌ Failed to write text: {str(e)}"


@tool(
    name="generate_final_interpretation",
    description="Generate a final interpretation/summary of the entire conversation session. This tool is typically called automatically at the end of a session. It analyzes all the conversation history and generates a comprehensive summary in Chinese and English.",
    parameters={},
    category="file_operations"
)
def generate_final_interpretation() -> str:
    """
    Generate a final interpretation/summary of the entire conversation session.
    Note: This tool is usually called automatically by the agent controller at session end.
    It reads the execution log to generate a summary.
    """
    try:
        from ..config.settings import get_session_artifacts_dir
        
        session_artifacts_dir = get_session_artifacts_dir()
        
        # Try to read execution log to get history
        import json
        from pathlib import Path
        
        # Find the execution log file
        log_files = list(session_artifacts_dir.glob("execution_log_*.json"))
        if not log_files:
            return "❌ No execution log found. Cannot generate interpretation."
        
        # Read the most recent log
        latest_log = sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        with open(latest_log, "r", encoding="utf-8") as f:
            log_data = json.load(f)
        
        history = log_data.get("history", [])
        
        # Generate basic summary from history
        summary_parts = []
        summary_parts.append("=" * 80)
        summary_parts.append("SESSION SUMMARY / 会话总结")
        summary_parts.append("=" * 80)
        summary_parts.append("")
        
        # Extract user instructions
        user_instructions = []
        for item in history:
            if item.get("role") == "user":
                content = item.get("content", "")
                # Try to parse JSON content
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "tool_execution" in parsed:
                        continue  # Skip tool execution results
                except:
                    pass
                if content and not content.startswith("{") and len(content) > 10:
                    user_instructions.append(content)
        
        if user_instructions:
            summary_parts.append("User Instructions / 用户指令:")
            summary_parts.append("-" * 80)
            for i, inst in enumerate(user_instructions, 1):
                summary_parts.append(f"{i}. {inst}")
            summary_parts.append("")
        
        # Extract key actions
        summary_parts.append("Key Actions / 关键操作:")
        summary_parts.append("-" * 80)
        action_count = {}
        for item in history:
            if item.get("role") == "assistant":
                content = item.get("content", "")
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "tool" in parsed:
                        tool_name = parsed.get("tool", "")
                        action_count[tool_name] = action_count.get(tool_name, 0) + 1
                except:
                    pass
        
        for tool_name, count in sorted(action_count.items()):
            summary_parts.append(f"- {tool_name}: {count} times")
        summary_parts.append("")
        
        # Extract results
        summary_parts.append("Results / 结果:")
        summary_parts.append("-" * 80)
        success_count = 0
        failure_count = 0
        for item in history:
            if item.get("role") == "user":
                content = item.get("content", "")
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "tool_execution" in parsed:
                        result = parsed.get("result", "")
                        if "✅" in result or "成功" in result:
                            success_count += 1
                        elif "❌" in result or "失败" in result:
                            failure_count += 1
                except:
                    pass
        
        summary_parts.append(f"- Successful operations: {success_count}")
        summary_parts.append(f"- Failed operations: {failure_count}")
        summary_parts.append("")
        
        summary_parts.append("=" * 80)
        summary_parts.append(f"Total Rounds: {log_data.get('total_rounds', 0)}")
        summary_parts.append(f"Session ID: {log_data.get('session_id', 'N/A')}")
        summary_parts.append(f"Timestamp: {log_data.get('timestamp', 'N/A')}")
        summary_parts.append("=" * 80)
        
        summary_text = "\n".join(summary_parts)
        
        # Save to file
        output_file = session_artifacts_dir / "session_summary.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(summary_text)
        
        # Use forward slashes in path display for better readability
        display_path = str(output_file).replace("\\", "/")
        return f"✅ Final interpretation generated and saved to: {display_path}"
    
    except Exception as e:
        return f"❌ Failed to generate final interpretation: {str(e)}"


@tool(
    name="ocr_image_to_text",
    description="Perform Optical Character Recognition (OCR) on an image file and save the extracted text to a new file. Provide only filenames (e.g., 'image.png', 'output.txt'), not directory paths.",
    parameters={
        "image_file_name": "string (required, filename only, e.g., 'scan.png')",
        "output_file_name": "string (required, filename only, e.g., 'recognized_text.txt')"
    },
    category="file_operations"
)
def ocr_image_to_text(image_file_name: str, output_file_name: str) -> str:
    """Perform OCR on an image file and save the extracted text to a new file."""
    try:
        # 实际运行时需要导入，这里假设它在执行环境中可用
        
        # 1. 规范化输入图片文件路径并检查
        image_path_obj = normalize_file_path(image_file_name, is_input=True)
        
        # 2. 如果文件不存在，尝试在常见子目录中搜索
        if not image_path_obj.exists():
            from ..config.settings import get_session_artifacts_dir
            session_artifacts_dir = get_session_artifacts_dir()
            # 尝试在常见子目录中查找
            common_dirs = ["extracted_images", "images", "output_images"]
            filename = Path(image_file_name).name  # 只取文件名
            
            for subdir in common_dirs:
                potential_path = session_artifacts_dir / subdir / filename
                if potential_path.exists():
                    image_path_obj = potential_path
                    break
            else:
                # 如果还是找不到，返回错误，但提供搜索建议
                search_hints = "\n".join([f"  - {subdir}/{filename}" for subdir in common_dirs])
                display_path = str(image_path_obj).replace("\\", "/")
                return (
                    f"❌ Image file not found at: {display_path}\n"
                    f"💡 Tried searching in common directories:\n{search_hints}\n"
                    f"💡 Please provide the full relative path (e.g., 'extracted_images/{filename}')"
                )
        
        # 2. 执行 OCR 识别
        # 使用 Pillow 打开图片，使用 pytesseract 提取文本
        img = Image.open(image_path_obj)
        # 您可以在这里添加语言配置，例如：pytesseract.image_to_string(img, lang='chi_sim')
        extracted_text = pytesseract.image_to_string(img)
        
        # 3. 规范化输出文本文件路径
        text_save_path_obj = normalize_file_path(output_file_name, is_input=False)
        
        # 4. 确保输出目录存在
        text_save_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        # 5. 将识别出的文本写入文件
        with open(text_save_path_obj, "w", encoding="utf-8") as f:
            f.write(extracted_text)
            
        # 6. 返回成功信息
        display_text_path = str(text_save_path_obj).replace("\\", "/")
        if extracted_text.strip():
            # 提取前50个字符作为预览
            preview = extracted_text.strip()[:50].replace('\n', ' ')
            return (
                f"✅ OCR completed successfully on {image_file_name}. "
                f"Text saved to: {display_text_path}\n"
                f"> Preview: '{preview}'..."
            )
        else:
            return f"⚠️ OCR completed, but no meaningful text was extracted from {image_file_name}. Text saved to: {display_text_path}"
        
    except ImportError as e:
        # 捕获 pytesseract 或 PIL 导入错误
        return f"❌ Failed to perform OCR. Required library missing: {e}. Please ensure 'pytesseract' and 'Pillow' are installed."
    except Exception as e:
        return f"❌ Failed to perform OCR or save text: {str(e)}"