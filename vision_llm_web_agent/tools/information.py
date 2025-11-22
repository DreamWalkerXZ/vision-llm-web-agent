"""
Information Gathering Tools
Tools for capturing screenshots, DOM, and page content
"""

from pathlib import Path
from .base import tool
from .browser_control import browser_state
from .dom_analyzer import semantic_dom_analyzer
from ..config.settings import ARTIFACTS_DIR


@tool(
    name="screenshot",
    description="Take a screenshot and save to path",
    parameters={"file_name": "string (required)"},
    category="information"
)
def take_screenshot(file_name: str = "screenshot.png") -> str:
    """Take a screenshot of the current page"""
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    try:
        # Normalize path to artifacts_dir/path (preserve subdirectories)
        save_path_obj = Path(file_name)
        if not save_path_obj.is_absolute():
            # Use artifacts_dir as base, preserving relative path structure
            save_path_obj = ARTIFACTS_DIR / save_path_obj
        save_path = str(save_path_obj)
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        browser_state.get_current_page().screenshot(path=save_path, full_page=False)
        return f"✅ Screenshot saved to: {save_path}"
    except Exception as e:
        return f"❌ Failed to take screenshot: {str(e)}"


@tool(
    name="dom_summary",
    description="Get simplified DOM structure with clickable elements. Returns text content and CSS selectors.",
    parameters={"max_elements": "int (optional, default: 50)"},
    category="information"
)
def get_dom_summary(max_elements: int = 50) -> str:
    """Get a simplified DOM structure focusing on clickable and interactive elements
    
    Note: This is a basic tool version. The agent controller uses semantic_dom_analyzer directly
    for enhanced DOM analysis with LLM filtering.
    """
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    try:
        # Use semantic analyzer without LLM filtering (model=None)
        result = semantic_dom_analyzer.analyze_page(
            browser_state.get_current_page(), 
            client=None, 
            user_prompt="", 
            model=None, 
            max_elements=max_elements
        )
        
        # Return text representation
        if isinstance(result, dict):
            return result.get("llm_text", "No DOM text available")
        else:
            return str(result)
    
    except Exception as e:
        return f"❌ Failed to get DOM summary: {str(e)}"


@tool(
    name="get_page_content",
    description="Get text content of current page",
    parameters={},
    category="information"
)
def get_page_text_content() -> str:
    """Get the text content of the current page"""
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    try:
        page = browser_state.get_current_page()
        content = page.evaluate("() => document.body.innerText")
        return content[:10000]
    except Exception as e:
        return f"❌ Failed to get page content: {str(e)}"
