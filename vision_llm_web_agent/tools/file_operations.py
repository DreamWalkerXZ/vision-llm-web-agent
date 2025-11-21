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
from ..config.settings import ARTIFACTS_DIR
import pytesseract


# file_operations.py (Updated)

def normalize_file_path(file_path: str, is_input: bool = False) -> Path:
    """
    Normalize file path to be relative to the ARTIFACTS_DIR, supporting nesting.
    """
    path_obj = Path(file_path)

    # 1. If path is absolute, use it directly (e.g., used by temp pytest fixtures)
    if path_obj.is_absolute():
        return path_obj
    
    # 2. If path is already rooted at ARTIFACTS_DIR, use it
    if path_obj.parts[0] == ARTIFACTS_DIR.name:
        # e.g., 'artifacts/test/file.pdf'
        return path_obj
    
    # 3. Otherwise, treat it as a path relative to ARTIFACTS_DIR (supports 'test/file.pdf')
    # This is the key change to support nested paths in tests
    full_path = ARTIFACTS_DIR / path_obj
    
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
    description="Download a PDF file from URL. Provide only the filename (e.g., 'abc.pdf'), not directory path.",
    parameters={
        "url": "string (required)",
        "file_name": "string (required, filename only, e.g., 'abc.pdf')"
    },
    category="file_operations"
)
def download_pdf_file(url: str, file_name: str) -> str:
    """Download a PDF file from a URL"""
    browser_state.initialize()
    
    try:
        # Normalize path to artifacts/filename (single level)
        save_path = normalize_file_path(file_name, is_input=False)
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Strategy 1: Use API request to fetch PDF directly (works best for direct PDF URLs like arXiv)
        try:
            response = browser_state.context.request.get(url, timeout=30000)
            if response.ok:
                pdf_content = response.body()
                
                # Verify it's actually a PDF
                if pdf_content.startswith(b'%PDF'):
                    with open(save_path, 'wb') as f:
                        f.write(pdf_content)
                    
                    size = Path(save_path).stat().st_size
                    return f"✅ PDF downloaded to: {save_path} (size: {size} bytes)"
                else:
                    # Not a PDF, try other strategies
                    pass
        except Exception:
            # Fall back to page navigation methods
            pass
        
        # Strategy 2: Try download event (for file download links)
        download_page = browser_state.context.new_page()
        
        try:
            with download_page.expect_download(timeout=5000) as download_info:
                download_page.goto(url, timeout=10000)
                download = download_info.value
                download.save_as(save_path)
                download_page.close()
                
                if Path(save_path).exists():
                    size = Path(save_path).stat().st_size
                    return f"✅ PDF downloaded to: {save_path} (size: {size} bytes)"
        except Exception:
            # If download event didn't trigger, the URL might not be a direct download
            pass
        
        download_page.close()
        return f"❌ Failed to download PDF from {url}"
    
    except Exception as e:
        return f"❌ Failed to download PDF: {str(e)}"


@tool(
    name="pdf_extract_text",
    description="Extract text from PDF file. Provide only the filename (e.g., 'abc.pdf'), not directory path.",
    parameters={
        "file_name": "string (required, filename only, e.g., 'abc.pdf')",
        "page_num": "int (optional, specific page)"
    },
    category="file_operations"
)
def extract_pdf_text(file_name: str, page_num: Optional[int] = None) -> str:
    """Extract text from a PDF file"""
    try:
        # Normalize path to artifacts/filename (single level)
        pdf_path = normalize_file_path(file_name, is_input=True)
        
        doc = pymupdf.open(pdf_path)
        
        if page_num is not None:
            if page_num >= len(doc):
                return f"❌ Page {page_num} does not exist. PDF has {len(doc)} pages."
            page = doc[page_num]
            text = page.get_text()
            doc.close()
            return f"Page {page_num}:\n{text}"
        else:
            text = ""
            for i, page in enumerate(doc):
                text += f"\n{'='*80}\nPage {i+1}:\n{'='*80}\n"
                text += page.get_text()
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
             return f"❌ PDF file not found at: {str(pdf_path_obj)}"
        
        doc = pymupdf.open(pdf_path_obj) # 使用 Path 对象
        saved_images = []
        
        pages_to_process = [page_num] if page_num is not None else range(len(doc))
        
        for page_idx in pages_to_process:
            if page_idx >= len(doc):
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
            # 5. 返回信息使用正确的目录路径
            return f"✅ Extracted {len(saved_images)} images to {str(output_dir_path)}:\n" + "\n".join(saved_images)
        else:
            return "⚠️ No images found in the PDF"
    
    except Exception as e:
        return f"❌ Failed to extract images from PDF: {str(e)}"


@tool(
    name="save_image",
    description="Save or crop an image. Provide only filenames (e.g., 'image.png'), not directory paths.",
    parameters={
        "file_name": "string (required, filename only, e.g., 'image.png')",
        "output_file_name": "string (optional, filename only, e.g., 'cropped.png')",
        "crop_box": "list (optional, [left, top, right, bottom])"
    },
    category="file_operations"
)
def save_or_crop_image(file_name: str, output_file_name: Optional[str] = None, 
                       crop_box: Optional[list] = None) -> str:
    """Save or crop an image"""
    try:
        # Normalize input image path to artifacts/filename (single level)
        image_path = normalize_file_path(file_name, is_input=True)
        
        img = Image.open(image_path)
        
        if crop_box:
            if len(crop_box) != 4:
                return "❌ crop_box must be [left, top, right, bottom]"
            img = img.crop(tuple(crop_box))
        
        # Normalize output path to artifacts/filename (single level)
        if output_file_name:
            save_path = normalize_file_path(output_file_name, is_input=False)
        else:
            # Use same filename as input
            save_path = normalize_file_path(Path(image_path).name, is_input=False)
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        img.save(save_path)
        return f"✅ Image saved to: {save_path}"
    
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
        
        return f"✅ Text written to: {file_path}"
    
    except Exception as e:
        return f"❌ Failed to write text: {str(e)}"

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
        
        if not image_path_obj.exists():
            return f"❌ Image file not found at: {str(image_path_obj)}"
        
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
        if extracted_text.strip():
            # 提取前50个字符作为预览
            preview = extracted_text.strip()[:50].replace('\n', ' ')
            return (
                f"✅ OCR completed successfully on {image_file_name}. "
                f"Text saved to: {str(text_save_path_obj)}\n"
                f"> Preview: '{preview}'..."
            )
        else:
            return f"⚠️ OCR completed, but no meaningful text was extracted from {image_file_name}. Text saved to: {str(text_save_path_obj)}"
        
    except ImportError as e:
        # 捕获 pytesseract 或 PIL 导入错误
        return f"❌ Failed to perform OCR. Required library missing: {e}. Please ensure 'pytesseract' and 'Pillow' are installed."
    except Exception as e:
        return f"❌ Failed to perform OCR or save text: {str(e)}"