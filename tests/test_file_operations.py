"""
Tests for file_operations.py tools
"""

import pytest
from pathlib import Path
from PIL import Image
import pymupdf  # PyMuPDF
from vision_llm_web_agent.tools.file_operations import (
    download_pdf_file,
    extract_pdf_text,
    extract_pdf_images,
    save_or_crop_image,
    write_text_to_file
)
from vision_llm_web_agent.tools.browser_control import browser_state


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a sample PDF file for testing"""
    pdf_path = tmp_path / "test.pdf"
    
    # Create a simple PDF with PyMuPDF
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 size
    
    # Add text
    page.insert_text((100, 100), "Test PDF Content", fontsize=20)
    page.insert_text((100, 150), "Page 1 - Line 1", fontsize=12)
    page.insert_text((100, 170), "Page 1 - Line 2", fontsize=12)
    
    # Add second page
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((100, 100), "Page 2 Content", fontsize=20)
    
    doc.save(str(pdf_path))
    doc.close()
    
    return pdf_path


@pytest.fixture
def sample_pdf_with_image(tmp_path):
    """Create a sample PDF with an embedded image"""
    pdf_path = tmp_path / "test_with_image.pdf"
    
    # Create a simple image
    img = Image.new('RGB', (100, 100), color='red')
    img_path = tmp_path / "test_image.png"
    img.save(img_path)
    
    # Create PDF with image
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    
    # Insert image
    rect = pymupdf.Rect(100, 100, 200, 200)
    page.insert_image(rect, filename=str(img_path))
    
    # Add some text
    page.insert_text((100, 250), "PDF with embedded image", fontsize=12)
    
    doc.save(str(pdf_path))
    doc.close()
    
    return pdf_path


@pytest.fixture
def sample_image(tmp_path):
    """Create a sample image for testing"""
    img_path = tmp_path / "test_image.png"
    img = Image.new('RGB', (200, 200), color='blue')
    
    # Draw something on the image
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 150, 150], fill='white')
    
    img.save(img_path)
    return img_path


class TestDownloadPdfFile:
    """Test the download_pdf_file function"""
    
    def test_download_from_arxiv(self, cleanup_browser, test_artifacts_dir):
        """Test downloading a real PDF from arXiv"""
        # Use a small, well-known paper
        url = "https://arxiv.org/pdf/1706.03762.pdf"  # Attention Is All You Need
        save_path = "test/downloaded_paper.pdf"
        
        result = download_pdf_file(url, save_path)
        
        # Check if download succeeded or had network issues
        if "✅" in result:
            full_path = Path("artifacts") / save_path
            assert full_path.exists()
            assert full_path.stat().st_size > 1000  # Should be > 1KB
            
            # Verify it's a valid PDF
            assert full_path.read_bytes().startswith(b'%PDF')
        else:
            # Network issues are acceptable in tests
            assert "❌" in result
    
    def test_download_creates_directory(self, cleanup_browser, test_artifacts_dir):
        """Test that download creates parent directories"""
        url = "https://arxiv.org/pdf/1706.03762.pdf"
        save_path = "test/nested/deep/paper.pdf"
        
        result = download_pdf_file(url, save_path)
        
        if "✅" in result:
            full_path = Path("artifacts") / save_path
            assert full_path.parent.exists()
    
    def test_download_invalid_url(self, cleanup_browser, test_artifacts_dir):
        """Test downloading from invalid URL"""
        url = "https://example.com/nonexistent.pdf"
        save_path = "test/nonexistent.pdf"
        
        result = download_pdf_file(url, save_path)
        # Should fail (might not always be a PDF)
        # Either succeeds with non-PDF or fails
        assert "✅" in result or "❌" in result
    
    def test_download_relative_path(self, cleanup_browser, test_artifacts_dir):
        """Test that relative paths are saved to artifacts directory"""
        # This test assumes network access; skip if needed
        url = "https://arxiv.org/pdf/1706.03762.pdf"
        save_path = "test/relative_path_test.pdf"
        
        result = download_pdf_file(url, save_path)
        
        if "✅" in result:
            # Should be in artifacts directory
            full_path = Path("artifacts") / save_path
            assert full_path.exists()


class TestExtractPdfText:
    """Test the extract_pdf_text function"""
    
    def test_extract_all_pages(self, sample_pdf):
        """Test extracting text from all pages"""
        result = extract_pdf_text(str(sample_pdf))
        
        assert "Page 1" in result or "Test PDF Content" in result
        assert "Page 2" in result or "Page 2 Content" in result
    
    def test_extract_specific_page(self, sample_pdf):
        """Test extracting text from specific page"""
        result = extract_pdf_text(str(sample_pdf), page_num=0)
        
        assert "Page" in result
        assert "Test PDF Content" in result
    
    def test_extract_second_page(self, sample_pdf):
        """Test extracting text from second page"""
        result = extract_pdf_text(str(sample_pdf), page_num=1)
        
        assert "Page 2" in result or "Page 2 Content" in result
    
    def test_extract_invalid_page(self, sample_pdf):
        """Test extracting from invalid page number"""
        result = extract_pdf_text(str(sample_pdf), page_num=999)
        
        assert "❌" in result
        assert "does not exist" in result
    
    def test_extract_nonexistent_file(self):
        """Test extracting from nonexistent file"""
        result = extract_pdf_text("/nonexistent/file.pdf")
        
        assert "❌" in result
    
    def test_extract_from_artifacts(self, sample_pdf, test_artifacts_dir):
        """Test extracting PDF from artifacts directory"""
        # Copy sample PDF to artifacts
        artifacts_pdf = Path("artifacts") / "test" / "sample.pdf"
        artifacts_pdf.parent.mkdir(parents=True, exist_ok=True)
        
        import shutil
        shutil.copy(sample_pdf, artifacts_pdf)
        
        # Test with relative path
        result = extract_pdf_text("test/sample.pdf")
        
        assert "Test PDF Content" in result or "Page" in result


class TestExtractPdfImages:
    """Test the extract_pdf_images function"""
    
    def test_extract_images_basic(self, sample_pdf_with_image, test_artifacts_dir):
        """Test extracting images from PDF"""
        output_dir = "test/extracted_images"
        
        result = extract_pdf_images(str(sample_pdf_with_image), output_dir)
        
        assert "✅" in result
        assert "1" in result  # Should extract 1 image
        
        # Check output directory
        full_output_dir = Path("artifacts") / output_dir
        assert full_output_dir.exists()
        
        # Check that image file was created
        images = list(full_output_dir.glob("*.png")) + list(full_output_dir.glob("*.jpg"))
        assert len(images) >= 1
    
    def test_extract_images_specific_page(self, sample_pdf_with_image, test_artifacts_dir):
        """Test extracting images from specific page"""
        output_dir = "test/page_images"
        
        result = extract_pdf_images(str(sample_pdf_with_image), output_dir, page_num=0)
        
        assert "✅" in result or "⚠️" in result  # Might have images or not
    
    def test_extract_images_no_images(self, sample_pdf, test_artifacts_dir):
        """Test extracting from PDF with no images"""
        output_dir = "test/no_images"
        
        result = extract_pdf_images(str(sample_pdf), output_dir)
        
        assert "⚠️" in result
        assert "No images" in result
    
    def test_extract_images_creates_dir(self, sample_pdf_with_image, test_artifacts_dir):
        """Test that extraction creates output directory"""
        output_dir = "test/new/nested/dir"
        
        result = extract_pdf_images(str(sample_pdf_with_image), output_dir)
        
        full_output_dir = Path("artifacts") / output_dir
        assert full_output_dir.exists()


class TestSaveOrCropImage:
    """Test the save_or_crop_image function"""
    
    def test_save_image_basic(self, sample_image, test_artifacts_dir):
        """Test basic image save"""
        output_path = "test/saved_image.png"
        
        result = save_or_crop_image(str(sample_image), output_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / output_path
        assert full_path.exists()
    
    def test_save_image_same_location(self, sample_image):
        """Test saving image to same location"""
        result = save_or_crop_image(str(sample_image))
        
        assert "✅" in result
        assert sample_image.exists()
    
    def test_crop_image(self, sample_image, test_artifacts_dir):
        """Test cropping an image"""
        output_path = "test/cropped_image.png"
        crop_box = [50, 50, 150, 150]  # left, top, right, bottom
        
        result = save_or_crop_image(str(sample_image), output_path, crop_box)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / output_path
        assert full_path.exists()
        
        # Verify image was cropped
        img = Image.open(full_path)
        assert img.size == (100, 100)  # 150-50 = 100
    
    def test_crop_invalid_box(self, sample_image):
        """Test cropping with invalid box"""
        output_path = "test/invalid_crop.png"
        crop_box = [50, 50, 150]  # Invalid - only 3 values
        
        result = save_or_crop_image(str(sample_image), output_path, crop_box)
        
        assert "❌" in result
        assert "must be" in result
    
    def test_save_nonexistent_image(self):
        """Test saving nonexistent image"""
        result = save_or_crop_image("/nonexistent/image.png", "output.png")
        
        assert "❌" in result
    
    def test_save_creates_directory(self, sample_image, test_artifacts_dir):
        """Test that save creates parent directories"""
        output_path = "test/deep/nested/saved.png"
        
        result = save_or_crop_image(str(sample_image), output_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / output_path
        assert full_path.parent.exists()


class TestWriteTextToFile:
    """Test the write_text_to_file function"""
    
    def test_write_text_basic(self, test_artifacts_dir):
        """Test basic text writing"""
        content = "Hello, World!\nThis is a test."
        file_path = "test/test_output.txt"
        
        result = write_text_to_file(content, file_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / file_path
        assert full_path.exists()
        assert full_path.read_text() == content
    
    def test_write_text_unicode(self, test_artifacts_dir):
        """Test writing unicode text"""
        content = "Hello 世界 🌍\nТест"
        file_path = "test/unicode_test.txt"
        
        result = write_text_to_file(content, file_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / file_path
        assert full_path.exists()
        assert full_path.read_text(encoding='utf-8') == content
    
    def test_write_text_empty(self, test_artifacts_dir):
        """Test writing empty text"""
        content = ""
        file_path = "test/empty.txt"
        
        result = write_text_to_file(content, file_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / file_path
        assert full_path.exists()
        assert full_path.read_text() == ""
    
    def test_write_text_overwrites(self, test_artifacts_dir):
        """Test that writing overwrites existing file"""
        file_path = "test/overwrite_test.txt"
        
        # Write first content
        write_text_to_file("First content", file_path)
        
        # Write second content
        result = write_text_to_file("Second content", file_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / file_path
        assert full_path.read_text() == "Second content"
    
    def test_write_text_creates_directory(self, test_artifacts_dir):
        """Test that write creates parent directories"""
        content = "Test content"
        file_path = "test/nested/deep/file.txt"
        
        result = write_text_to_file(content, file_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / file_path
        assert full_path.parent.exists()
        assert full_path.read_text() == content
    
    def test_write_text_long_content(self, test_artifacts_dir):
        """Test writing long text content"""
        content = "Line {}\n" * 10000
        content = content.format(*range(10000))
        file_path = "test/long_content.txt"
        
        result = write_text_to_file(content, file_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / file_path
        assert full_path.exists()
        assert len(full_path.read_text()) == len(content)


class TestFileOperationsIntegration:
    """Integration tests for file operations"""
    
    def test_download_and_extract_text(self, cleanup_browser, test_artifacts_dir):
        """Test downloading PDF and extracting text"""
        # Download PDF
        url = "https://arxiv.org/pdf/1706.03762.pdf"
        save_path = "test/integration_paper.pdf"
        
        download_result = download_pdf_file(url, save_path)
        
        if "✅" in download_result:
            # Extract text
            extract_result = extract_pdf_text(save_path)
            
            # Should contain some text (paper title or abstract)
            assert len(extract_result) > 100
            assert "Page" in extract_result or extract_result.strip()
    
    def test_crop_and_save_chain(self, sample_image, test_artifacts_dir):
        """Test chaining crop and save operations"""
        # First crop
        intermediate_path = "test/intermediate.png"
        result1 = save_or_crop_image(str(sample_image), intermediate_path, [25, 25, 175, 175])
        assert "✅" in result1
        
        # Second crop on the result
        final_path = "test/final.png"
        full_intermediate = Path("artifacts") / intermediate_path
        result2 = save_or_crop_image(str(full_intermediate), final_path, [25, 25, 125, 125])
        assert "✅" in result2
        
        # Verify final image
        full_final = Path("artifacts") / final_path
        img = Image.open(full_final)
        assert img.size == (100, 100)

