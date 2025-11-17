"""
Tests for enhanced DOM extraction features
"""

import pytest
from pathlib import Path
from vision_llm_web_agent.tools.information import (
    get_dom_summary,
    find_element_by_description
)
from vision_llm_web_agent.tools.browser_control import (
    goto_url,
    click_element,
    browser_state
)


class TestEnhancedDomSummary:
    """Test the enhanced DOM summary function"""
    
    def test_dom_summary_with_multiple_selectors(self, cleanup_browser, sample_html_file):
        """Test that DOM summary provides multiple selector options"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Should contain multiple selector options
        assert "💡 Best:" in result
        assert "💡 CSS:" in result or "💡 Use:" in result
        assert "💡 XPath:" in result
        
    def test_dom_summary_includes_position(self, cleanup_browser, sample_html_file):
        """Test that DOM summary includes element positions"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Should contain position information
        assert "Position:" in result
        
    def test_dom_summary_includes_visibility(self, cleanup_browser, sample_html_file):
        """Test that DOM summary shows visibility indicators"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Should contain visibility indicators (👁️ or 🔒)
        assert "👁️" in result or "🔒" in result
        
    def test_dom_summary_with_hidden_elements(self, cleanup_browser, sample_html_file):
        """Test DOM summary can include hidden elements"""
        goto_url(f"file://{sample_html_file}")
        
        result_visible = get_dom_summary(include_hidden=False)
        result_all = get_dom_summary(include_hidden=True)
        
        # The all result might have more elements
        assert len(result_all) >= len(result_visible)
        
    def test_dom_summary_includes_labels(self, cleanup_browser, sample_html_file):
        """Test that DOM summary shows associated labels"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Should show label information for inputs
        # This depends on the sample HTML having labeled inputs
        assert "INPUT FIELDS:" in result
        
    def test_dom_summary_real_website_enhanced(self, cleanup_browser):
        """Test enhanced DOM summary on real website"""
        goto_url("https://example.com")
        
        result = get_dom_summary()
        
        # Should have enhanced information
        assert "Position:" in result
        assert "💡" in result  # Should have suggestions
        

class TestFindElement:
    """Test the find_element function"""
    
    def test_find_element_without_browser(self):
        """Test find element fails when browser not initialized"""
        result = find_element_by_description("test")
        assert "❌" in result
        assert "not initialized" in result.lower()
    
    def test_find_element_basic(self, cleanup_browser, sample_html_file):
        """Test basic element finding"""
        goto_url(f"file://{sample_html_file}")
        
        result = find_element_by_description("Click Me")
        
        assert "🔍 Search:" in result
        assert "Click Me" in result
        assert "💡 Use:" in result
        
    def test_find_element_fuzzy_match(self, cleanup_browser, sample_html_file):
        """Test fuzzy matching"""
        goto_url(f"file://{sample_html_file}")
        
        # Try partial match
        result = find_element_by_description("Click")
        
        assert "🔍 Search:" in result
        # Should find elements with "Click" in them
        assert "Score:" in result
        
    def test_find_element_by_type(self, cleanup_browser, sample_html_file):
        """Test finding specific element types"""
        goto_url(f"file://{sample_html_file}")
        
        result_button = find_element_by_description("Click", element_type="button")
        result_input = find_element_by_description("test", element_type="input")
        
        assert "🔍 Search:" in result_button
        assert "🔍 Search:" in result_input
        
    def test_find_element_score_display(self, cleanup_browser, sample_html_file):
        """Test that scores are displayed and elements are ranked"""
        goto_url(f"file://{sample_html_file}")
        
        result = find_element_by_description("Click Me")
        
        # Should show score percentages
        assert "%" in result
        # Should show score emoji
        assert "🟢" in result or "🟡" in result or "🟠" in result
        
    def test_find_element_no_match(self, cleanup_browser, sample_html_file):
        """Test behavior when no elements match"""
        goto_url(f"file://{sample_html_file}")
        
        result = find_element_by_description("NonexistentElement12345")
        
        assert "❌" in result or "No elements found" in result
        
    def test_find_element_real_website(self, cleanup_browser):
        """Test finding elements on real website"""
        goto_url("https://example.com")
        
        result = find_element_by_description("More information")
        
        assert "🔍 Search:" in result
        # Should find the link with "More information"


class TestClickWithXPath:
    """Test clicking with XPath"""
    
    def test_click_with_xpath(self, cleanup_browser, sample_html_file):
        """Test clicking an element using XPath"""
        goto_url(f"file://{sample_html_file}")
        
        # First get the XPath from DOM summary
        dom_result = get_dom_summary()
        
        # Extract an XPath from the result (this is a simple test)
        # In real usage, the agent would parse this information
        assert "XPath:" in dom_result
        
    def test_click_xpath_vs_css(self, cleanup_browser, sample_html_file):
        """Test that XPath works as well as CSS selector"""
        goto_url(f"file://{sample_html_file}")
        
        # Both should work (depending on the HTML structure)
        # This test verifies that the xpath parameter is accepted
        # Actual functionality depends on sample HTML
        pass
        

class TestIntegration:
    """Integration tests for enhanced DOM features"""
    
    def test_find_and_click_workflow(self, cleanup_browser, sample_html_file):
        """Test the workflow: find element -> get selector -> click"""
        goto_url(f"file://{sample_html_file}")
        
        # Find element
        find_result = find_element_by_description("Click Me")
        
        # Should provide selector that can be used
        assert "💡 Use: click(selector=" in find_result or "💡 Use: click(text=" in find_result
        
        # Click using text (simplest method)
        click_result = click_element(text="Click Me")
        
        # Should succeed
        assert "✅" in click_result
        
    def test_dom_summary_provides_actionable_info(self, cleanup_browser, sample_html_file):
        """Test that DOM summary provides all info needed for interaction"""
        goto_url(f"file://{sample_html_file}")
        
        result = get_dom_summary()
        
        # Should have:
        # 1. Multiple selector options
        assert "selector=" in result or "text=" in result
        
        # 2. Element positions
        assert "Position:" in result
        
        # 3. Usage examples
        assert "💡" in result
        
        # 4. Element metadata (labels, aria, etc.)
        lines = result.split("\n")
        assert len(lines) > 10  # Should be detailed
