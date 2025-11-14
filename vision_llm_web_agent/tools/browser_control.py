"""
Browser Control Tools
Tools for basic browser navigation and interaction
"""

import time
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

from .base import tool


# ============================================================================
# Browser State Management
# ============================================================================

class BrowserState:
    """Manages the global browser state"""
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_initialized = False
    
    def initialize(self, headless: bool = False):
        """Initialize browser if not already initialized"""
        if self.is_initialized:
            return
        
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US"
        )
        self.page = self.context.new_page()
        self.is_initialized = True
        print("✅ Browser initialized")
    
    def cleanup(self):
        """Clean up browser resources"""
        try:
            if self.page:
                self.page.close()
        except Exception:
            pass  # Page might already be closed
        
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass  # Context might already be closed
        
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass  # Browser might already be closed
        
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass  # Playwright might already be stopped
        
        self.is_initialized = False
        print("✅ Browser cleaned up")

    def get_current_page(self) -> Optional[Page]:
        """Return the current active page (last opened one)"""
        context = browser_state.page.context if browser_state.page else None
        if context:
            pages = context.pages
            if pages:
                return pages[-1]  # 最新打开的页面
        return browser_state.page  # fallback


# Global browser instance
browser_state = BrowserState()


# ============================================================================
# Browser Control Tools
# ============================================================================

@tool(
    name="goto",
    description="Navigate to a URL",
    parameters={"url": "string (required)"},
    category="browser_control"
)
def goto_url(url: str) -> str:
    """Navigate to a URL"""
    browser_state.initialize()
    
    try:
        response = browser_state.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        final_url = browser_state.page.url
        status = response.status if response else "unknown"
        return f"✅ Navigated to {final_url} (status: {status})"
    except Exception as e:
        return f"❌ Failed to navigate to {url}: {str(e)}"


@tool(
    name="click",
    description="Click an element by text content or CSS selector. PREFER text when possible for better reliability.",
    parameters={
        "selector": "string (optional) - CSS selector",
        "text": "string (optional) - Text content to search for",
        "exact": "boolean (optional, default: false) - Whether to match text exactly"
    },
    category="browser_control"
)
def click_element(selector: str = None, text: str = None, exact: bool = False) -> str:
    """Click an element by CSS selector or text content"""
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    if not selector and not text:
        return "❌ Either selector or text must be provided"
    
    try:
        # Record URL before click
        url_before = browser_state.page.url
        
        # Determine which locator strategy to use
        if text:
            # Use text-based locator (more reliable)
            if exact:
                elements = browser_state.page.get_by_text(text, exact=True)
                locator_desc = f"text (exact): '{text}'"
            else:
                elements = browser_state.page.get_by_text(text, exact=False)
                locator_desc = f"text: '{text}'"
        else:
            # Use CSS selector
            elements = browser_state.page.locator(selector)
            locator_desc = f"selector: {selector}"
        
        count = elements.count()
        click_result = None
        
        if count == 0:
            return f"❌ No elements found with {locator_desc}"
        elif count > 1:
            # If multiple elements, try to find one that works
            last_success_no_nav = None
            for i in range(count):
                try:
                    element = elements.nth(i)
                    url_before_click = browser_state.page.url
                    
                    # Try to detect navigation and wait for it
                    try:
                        with browser_state.page.expect_navigation(timeout=3000, wait_until="domcontentloaded"):
                            element.click(timeout=5000)
                        # Navigation occurred - this is likely the right element
                        click_result = f"✅ Clicked element {i+1}/{count} with {locator_desc}"
                        break
                    except Exception:
                        # Check if URL changed without navigation event
                        time.sleep(0.5)
                        url_after = browser_state.page.url
                        if url_after != url_before_click:
                            # URL changed, this was successful
                            click_result = f"✅ Clicked element {i+1}/{count} with {locator_desc}"
                            break
                        else:
                            # No navigation - save this as fallback but try next element
                            last_success_no_nav = f"✅ Clicked element {i+1}/{count} with {locator_desc} (no navigation)"
                            continue
                except Exception:
                    # Click failed, try next element
                    continue
            
            # If we didn't break (no navigation found), use the last successful click
            if not click_result:
                if last_success_no_nav:
                    click_result = last_success_no_nav
                else:
                    return f"❌ Failed to click any of {count} elements with {locator_desc}"
        else:
            # Single element - try to detect and wait for navigation
            try:
                with browser_state.page.expect_navigation(timeout=3000, wait_until="domcontentloaded"):
                    elements.click(timeout=5000)
                click_result = f"✅ Clicked element with {locator_desc}"
            except Exception:
                # No navigation occurred or timeout, that's fine
                # The element was still clicked successfully
                click_result = f"✅ Clicked element with {locator_desc}"
        
        # Check if URL changed
        url_after = browser_state.page.url
        if url_before != url_after:
            return f"{click_result} → Navigated to: {url_after}"
        else:
            return f"{click_result} (Page URL unchanged: {url_after})"
            
    except Exception as e:
        if text:
            return f"❌ Failed to click element with text '{text}': {str(e)}"
        else:
            return f"❌ Failed to click {selector}: {str(e)}"


@tool(
    name="type_text",
    description="Type text into an input field",
    parameters={
        "selector": "string (required)",
        "text": "string (required)",
        "clear_first": "boolean (optional, default: true)"
    },
    category="browser_control"
)
def type_into_element(selector: str, text: str, clear_first: bool = True) -> str:
    """Type text into an input field"""
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    try:
        # Wait longer for the element to be available
        browser_state.page.wait_for_selector(selector, timeout=10000, state="visible")
        
        # Focus on the element (this replaces the need for clicking)
        browser_state.page.focus(selector)
        
        if clear_first:
            browser_state.page.fill(selector, "")
        
        # Type the text
        browser_state.page.type(selector, text, delay=50)  # Add small delay between keystrokes
        return f"✅ Typed '{text}' into {selector}"
    except Exception as e:
        return f"❌ Failed to type into {selector}: {str(e)}"


@tool(
    name="press_key",
    description="Press a keyboard key (e.g., 'Enter', 'Escape')",
    parameters={"key": "string (required)"},
    category="browser_control"
)
def press_keyboard_key(key: str) -> str:
    """Press a keyboard key"""
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    try:
        url_before = browser_state.page.url
        
        # Try to detect navigation and wait for it (e.g., pressing Enter on a form)
        try:
            with browser_state.page.expect_navigation(timeout=3000, wait_until="domcontentloaded"):
                browser_state.page.keyboard.press(key)
            # Navigation occurred
            url_after = browser_state.page.url
            if url_before != url_after:
                return f"✅ Pressed key: {key} → Navigated to: {url_after}"
            else:
                return f"✅ Pressed key: {key} (Page reloaded)"
        except Exception:
            # No navigation occurred, that's fine
            url_after = browser_state.page.url
            if url_before != url_after:
                return f"✅ Pressed key: {key} → URL changed to: {url_after}"
            else:
                return f"✅ Pressed key: {key}"
    except Exception as e:
        return f"❌ Failed to press key {key}: {str(e)}"


@tool(
    name="scroll",
    description="Scroll the page",
    parameters={
        "direction": "string (optional, default: 'down')",
        "amount": "int (optional, default: 500)"
    },
    category="browser_control"
)
def scroll_page(direction: str = "down", amount: int = 500) -> str:
    """Scroll the page"""
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    try:
        if direction == "down":
            browser_state.page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            browser_state.page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "right":
            browser_state.page.evaluate(f"window.scrollBy({amount}, 0)")
        elif direction == "left":
            browser_state.page.evaluate(f"window.scrollBy(-{amount}, 0)")
        else:
            return f"❌ Invalid direction: {direction}"
        
        return f"✅ Scrolled {direction} by {amount}px"
    except Exception as e:
        return f"❌ Failed to scroll: {str(e)}"


@tool(
    name="close_browser",
    description="Close the browser and clean up resources",
    parameters={},
    category="browser_control"
)
def close_browser_instance() -> str:
    """Close the browser and clean up resources"""
    browser_state.cleanup()
    return "✅ Browser closed"
