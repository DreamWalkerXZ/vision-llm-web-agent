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


def normalize_file_path(file_path: str, is_input: bool = False) -> str:
    """
    Normalize file path to artifacts/filename format (single level, no nesting).
    
    Args:
        file_path: File path provided by agent (should be just filename like "abc.pdf")
        is_input: If True, this is an input file path (for reading). If False, output path (for saving).
    
    Returns:
        Normalized path in format "artifacts_dir/filename" (single level)
    """
    # Extract filename from any path format (remove all directory prefixes)
    path_obj = Path(file_path)
    filename = path_obj.name
    
    # Get artifacts directory as string for comparison
    artifacts_dir_str = str(ARTIFACTS_DIR)
    
    # For input files, try to find in artifacts or current directory
    if is_input:
        # Try artifacts_dir/filename first
        artifacts_path = ARTIFACTS_DIR / filename
        if artifacts_path.exists():
            return str(artifacts_path)
        # Try original path as-is (might be absolute or relative with artifacts/)
        if path_obj.exists():
            return str(path_obj)
        # Try with artifacts_dir prefix if original path had it
        if file_path.startswith(artifacts_dir_str + "/") or file_path.startswith("artifacts/"):
            artifacts_path = Path(file_path)
            if artifacts_path.exists():
                return str(artifacts_path)
        # Return artifacts_dir/filename as default (will fail if file doesn't exist)
        return str(artifacts_path)
    else:
        # For output files, always use artifacts_dir/filename (single level, no nesting)
        return str(ARTIFACTS_DIR / filename)


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
        # Normalize PDF path to artifacts/filename (single level)
        pdf_path = normalize_file_path(file_name, is_input=True)
        
        # For output directory, extract just the name and use artifacts_dir/dirname
        output_dir_obj = Path(output_dir)
        dirname = output_dir_obj.name if output_dir_obj.name else output_dir
        output_dir = str(ARTIFACTS_DIR / dirname)
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        doc = pymupdf.open(pdf_path)
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
                image_path = Path(output_dir) / image_filename
                
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                saved_images.append(str(image_path))
        
        doc.close()
        
        if saved_images:
            return f"✅ Extracted {len(saved_images)} images to {output_dir}:\n" + "\n".join(saved_images)
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
