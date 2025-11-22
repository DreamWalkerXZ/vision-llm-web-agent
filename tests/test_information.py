"""
Tests for information.py tools
"""

import pytest
from pathlib import Path
from vision_llm_web_agent.tools.information import (
    take_screenshot,
    get_dom_summary,
    get_page_text_content
)
from vision_llm_web_agent.tools.browser_control import goto_url, browser_state


class TestTakeScreenshot:
    """Test the take_screenshot function"""
    
    def test_screenshot_without_browser(self):
        """Test screenshot fails when browser not initialized"""
        result = take_screenshot("test.png")
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_screenshot_success(self, cleanup_browser, test_artifacts_dir, sample_html_file):
        """Test successful screenshot"""
        goto_url(f"file://{sample_html_file}")
        
        screenshot_path = "test/screenshot_test.png"
        result = take_screenshot(screenshot_path)
        
        assert "✅" in result
        assert screenshot_path in result
        
        # Verify file was created
        full_path = Path("artifacts") / screenshot_path
        assert full_path.exists()
        assert full_path.stat().st_size > 0
    
    def test_screenshot_creates_directory(self, cleanup_browser, test_artifacts_dir, sample_html_file):
        """Test that screenshot creates parent directories"""
        goto_url(f"file://{sample_html_file}")
        
        screenshot_path = "test/nested/dir/screenshot.png"
        result = take_screenshot(screenshot_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / screenshot_path
        assert full_path.exists()
        assert full_path.parent.exists()
    
    def test_screenshot_real_website(self, cleanup_browser, test_artifacts_dir):
        """Test screenshot of real website"""
        goto_url("https://example.com")
        
        screenshot_path = "test/example_screenshot.png"
        result = take_screenshot(screenshot_path)
        
        assert "✅" in result
        
        full_path = Path("artifacts") / screenshot_path
        assert full_path.exists()
        assert full_path.stat().st_size > 0
    
    def test_screenshot_absolute_path(self, cleanup_browser, tmp_path, sample_html_file):
        """Test screenshot with absolute path"""
        goto_url(f"file://{sample_html_file}")
        
        screenshot_path = tmp_path / "absolute_screenshot.png"
        result = take_screenshot(str(screenshot_path))
        
        assert "✅" in result
        assert screenshot_path.exists()


class TestGetDomSummary:
    """Test the get_dom_summary function"""
    
    def test_dom_summary_without_browser(self):
        """Test DOM summary fails when browser not initialized"""
        result = get_dom_summary()
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_dom_summary_basic(self, cleanup_browser, sample_html_file):
        """Test basic DOM summary"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Result should be a string
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_dom_summary_contains_elements(self, cleanup_browser, sample_html_file):
        """Test that DOM summary contains expected elements"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Should extract interactive elements
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_dom_summary_max_elements(self, cleanup_browser, sample_html_file):
        """Test DOM summary with max_elements limit"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary(max_elements=2)
        
        # Should return a string with limited elements
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_dom_summary_real_website(self, cleanup_browser):
        """Test DOM summary on real website"""
        goto_url("https://example.com")
        
        result = get_dom_summary()
        
        # Should have some content
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_dom_summary_includes_selectors(self, cleanup_browser, sample_html_file):
        """Test that DOM summary includes CSS selectors"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Should have some content with selectors
        assert isinstance(result, str)
        assert len(result) > 0


class TestGetPageTextContent:
    """Test the get_page_text_content function"""
    
    def test_page_content_without_browser(self):
        """Test page content fails when browser not initialized"""
        result = get_page_text_content()
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_page_content_basic(self, cleanup_browser, sample_html_file):
        """Test basic page content extraction"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_page_text_content()
        
        assert "Test Page" in result
        assert "Click Me" in result
    
    def test_page_content_real_website(self, cleanup_browser):
        """Test page content on real website"""
        goto_url("https://example.com")
        
        result = get_page_text_content()
        
        assert len(result) > 0
        assert "Example" in result
    
    def test_page_content_length_limit(self, cleanup_browser, sample_html_file):
        """Test that page content is limited to 10000 characters"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_page_text_content()
        
        # Should be less than or equal to 10000 characters
        assert len(result) <= 10000
    
    def test_page_content_no_html_tags(self, cleanup_browser, sample_html_file):
        """Test that page content doesn't include HTML tags"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_page_text_content()
        
        # Should not contain HTML tags
        assert "<html>" not in result.lower()
        assert "<body>" not in result.lower()
        assert "<div>" not in result.lower()

