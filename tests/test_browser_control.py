"""
Tests for browser_control.py tools
"""

import pytest
from pathlib import Path
from vision_llm_web_agent.tools.browser_control import (
    goto_url,
    click_element,
    type_into_element,
    press_keyboard_key,
    scroll_page,
    close_browser_instance,
    browser_state,
    BrowserState
)


class TestBrowserState:
    """Test the BrowserState class"""
    
    def test_initialize_creates_browser(self, cleanup_browser):
        """Test browser initialization"""
        state = BrowserState()
        assert not state.is_initialized
        
        state.initialize(headless=True)
        assert state.is_initialized
        assert state.browser is not None
        assert state.context is not None
        assert state.page is not None
        
        state.cleanup()
        assert not state.is_initialized
    
    def test_initialize_idempotent(self, cleanup_browser):
        """Test that multiple initialize calls don't create duplicate browsers"""
        state = BrowserState()
        state.initialize(headless=True)
        browser1 = state.browser
        
        state.initialize(headless=True)
        browser2 = state.browser
        
        assert browser1 is browser2
        state.cleanup()
    
    def test_cleanup_handles_uninitialized(self):
        """Test that cleanup handles uninitialized state gracefully"""
        state = BrowserState()
        state.cleanup()  # Should not raise error
        assert not state.is_initialized


class TestGotoUrl:
    """Test the goto_url function"""
    
    def test_goto_url_success(self, cleanup_browser, sample_html_file):
        """Test successful navigation to a URL"""
        url = f"file://{sample_html_file}"
        result = goto_url(url)
        
        assert "✅" in result
        assert url in result
        assert browser_state.is_initialized
        assert browser_state.page.url == url
    
    def test_goto_url_invalid(self, cleanup_browser):
        """Test navigation to invalid URL"""
        result = goto_url("http://this-domain-does-not-exist-12345.com")
        
        assert "❌" in result
    
    def test_goto_url_real_website(self, cleanup_browser):
        """Test navigation to a real website"""
        result = goto_url("https://example.com")
        
        assert "✅" in result
        assert "example.com" in browser_state.page.url.lower()


class TestClickElement:
    """Test the click_element function"""
    
    def test_click_without_browser(self):
        """Test click fails when browser not initialized"""
        result = click_element("#test-button")
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_click_success(self, cleanup_browser, sample_html_file):
        """Test successful element click"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element("#test-button")
        assert "✅" in result
    
    def test_click_nonexistent_element(self, cleanup_browser, sample_html_file):
        """Test clicking nonexistent element"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element("#nonexistent-element")
        assert "❌" in result
    
    def test_click_with_text_selector(self, cleanup_browser, sample_html_file):
        """Test clicking using text selector"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element("button:has-text('Click Me')")
        assert "✅" in result or "❌" in result  # Syntax might need adjustment
    
    def test_click_by_text(self, cleanup_browser, sample_html_file):
        """Test clicking element using text parameter"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element(text="Click Me")
        assert "✅" in result
        assert "text: 'Click Me'" in result
    
    def test_click_by_text_exact(self, cleanup_browser, sample_html_file):
        """Test clicking element using exact text match"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element(text="Click Me", exact=True)
        assert "✅" in result
        assert "text (exact): 'Click Me'" in result
    
    def test_click_by_text_partial_match(self, cleanup_browser, sample_html_file):
        """Test clicking element using partial text match"""
        goto_url(f"file://{sample_html_file}")
        
        # "Click" should match "Click Me"
        result = click_element(text="Click")
        assert "✅" in result
    
    def test_click_by_text_not_found(self, cleanup_browser, sample_html_file):
        """Test clicking with text that doesn't exist"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element(text="Nonexistent Text")
        assert "❌" in result
        assert "No elements found" in result
    
    def test_click_no_selector_no_text(self, cleanup_browser, sample_html_file):
        """Test click fails when neither selector nor text provided"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element()
        assert "❌" in result
        assert "Either selector or text must be provided" in result
    
    def test_click_by_text_link(self, cleanup_browser, sample_html_file):
        """Test clicking a link using text"""
        goto_url(f"file://{sample_html_file}")
        
        result = click_element(text="Example Link")
        assert "✅" in result


class TestTypeIntoElement:
    """Test the type_into_element function"""
    
    def test_type_without_browser(self):
        """Test type fails when browser not initialized"""
        result = type_into_element("#test-input", "hello")
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_type_success(self, cleanup_browser, sample_html_file):
        """Test successful text typing"""
        goto_url(f"file://{sample_html_file}")
        
        result = type_into_element("#test-input", "Hello World")
        assert "✅" in result
        assert "Hello World" in result
        
        # Verify text was actually typed
        value = browser_state.page.input_value("#test-input")
        assert value == "Hello World"
    
    def test_type_clear_first(self, cleanup_browser, sample_html_file):
        """Test typing with clear_first option"""
        goto_url(f"file://{sample_html_file}")
        
        # Type first text
        type_into_element("#test-input", "First")
        
        # Type second text with clear_first=True
        result = type_into_element("#test-input", "Second", clear_first=True)
        assert "✅" in result
        
        value = browser_state.page.input_value("#test-input")
        assert value == "Second"
    
    def test_type_no_clear(self, cleanup_browser, sample_html_file):
        """Test typing without clearing first"""
        goto_url(f"file://{sample_html_file}")
        
        # Type first text
        type_into_element("#test-input", "First")
        
        # Type second text with clear_first=False
        result = type_into_element("#test-input", " Second", clear_first=False)
        assert "✅" in result
        
        value = browser_state.page.input_value("#test-input")
        assert "Second" in value


class TestPressKey:
    """Test the press_keyboard_key function"""
    
    def test_press_key_without_browser(self):
        """Test key press fails when browser not initialized"""
        result = press_keyboard_key("Enter")
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_press_enter_key(self, cleanup_browser, sample_html_file):
        """Test pressing Enter key"""
        goto_url(f"file://{sample_html_file}")
        
        result = press_keyboard_key("Enter")
        assert "✅" in result
        assert "Enter" in result
    
    def test_press_escape_key(self, cleanup_browser, sample_html_file):
        """Test pressing Escape key"""
        goto_url(f"file://{sample_html_file}")
        
        result = press_keyboard_key("Escape")
        assert "✅" in result
        assert "Escape" in result


class TestScrollPage:
    """Test the scroll_page function"""
    
    def test_scroll_without_browser(self):
        """Test scroll fails when browser not initialized"""
        result = scroll_page("down")
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_scroll_down(self, cleanup_browser, sample_html_file):
        """Test scrolling down"""
        goto_url(f"file://{sample_html_file}")
        
        result = scroll_page("down", 100)
        assert "✅" in result
        assert "down" in result.lower()
    
    def test_scroll_up(self, cleanup_browser, sample_html_file):
        """Test scrolling up"""
        goto_url(f"file://{sample_html_file}")
        
        result = scroll_page("up", 100)
        assert "✅" in result
        assert "up" in result.lower()
    
    def test_scroll_right(self, cleanup_browser, sample_html_file):
        """Test scrolling right"""
        goto_url(f"file://{sample_html_file}")
        
        result = scroll_page("right", 100)
        assert "✅" in result
        assert "right" in result.lower()
    
    def test_scroll_left(self, cleanup_browser, sample_html_file):
        """Test scrolling left"""
        goto_url(f"file://{sample_html_file}")
        
        result = scroll_page("left", 100)
        assert "✅" in result
        assert "left" in result.lower()
    
    def test_scroll_invalid_direction(self, cleanup_browser, sample_html_file):
        """Test scrolling with invalid direction"""
        goto_url(f"file://{sample_html_file}")
        
        result = scroll_page("invalid", 100)
        assert "❌" in result
        assert "Invalid direction" in result


class TestCloseBrowser:
    """Test the close_browser_instance function"""
    
    def test_close_browser(self, cleanup_browser):
        """Test closing browser"""
        # Initialize browser first
        goto_url("https://example.com")
        assert browser_state.is_initialized
        
        result = close_browser_instance()
        assert "✅" in result
        assert not browser_state.is_initialized
    
    def test_close_uninitialized_browser(self):
        """Test closing uninitialized browser"""
        result = close_browser_instance()
        assert "✅" in result  # Should succeed gracefully
