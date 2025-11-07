"""
Information Gathering Tools
Tools for capturing screenshots, DOM, and page content
"""

from pathlib import Path
from .base import tool
from .browser_control import browser_state
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
        # Normalize path to artifacts_dir/filename (single level)
        save_path_obj = Path(file_name)
        if not save_path_obj.is_absolute():
            # Extract filename and use artifacts_dir
            filename = save_path_obj.name
            save_path_obj = ARTIFACTS_DIR / filename
        save_path = str(save_path_obj)
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        browser_state.page.screenshot(path=save_path, full_page=False)
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
    """Get a simplified DOM structure focusing on clickable and interactive elements"""
    if not browser_state.is_initialized:
        return "❌ Browser not initialized. Call goto() first."
    
    try:
        # JavaScript to extract interactive elements with better organization
        dom_script = """
        () => {
            const result = {
                buttons: [],
                links: [],
                inputs: [],
                selects: [],
                other: []
            };
            
            // Helper to check visibility
            const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && 
                       rect.height > 0 && 
                       style.display !== 'none' && 
                       style.visibility !== 'hidden' &&
                       style.opacity !== '0';
            };
            
            // Helper to get clean text
            const getCleanText = (el) => {
                const text = el.innerText || el.textContent || el.value || el.placeholder || el.alt || el.title || '';
                return text.trim().replace(/\\s+/g, ' ').substring(0, 80);
            };
            
            // Helper to check if a class name looks like it's dynamically generated
            const isDynamicClass = (className) => {
                // Check for hash-like patterns: __H9gR5, _1a2b3c, etc.
                return /(__[A-Za-z0-9]{5,}|_[a-f0-9]{6,})/i.test(className);
            };
            
            // Helper to build CSS selector
            const buildSelector = (el, includeAttr = true) => {
                const tag = el.tagName.toLowerCase();
                if (el.id) return `#${el.id}`;
                if (el.name) return `${tag}[name="${el.name}"]`;
                
                // For input/textarea, prefer attribute-based selectors
                if ((tag === 'input' || tag === 'textarea') && includeAttr) {
                    if (el.placeholder) return `${tag}[placeholder="${el.placeholder}"]`;
                    if (el.type && tag === 'input') return `input[type="${el.type}"]`;
                }
                
                // Build class selector, but avoid dynamic classes
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.trim().split(/\\s+/)
                        .filter(c => c && !isDynamicClass(c));
                    if (classes.length > 0) {
                        return `${tag}.${classes.slice(0, 2).join('.')}`;
                    }
                }
                
                // For buttons with aria-label
                if (el.getAttribute('aria-label')) {
                    return `${tag}[aria-label="${el.getAttribute('aria-label')}"]`;
                }
                
                return tag;
            };
            
            // Collect buttons (including role="button")
            document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]').forEach(el => {
                if (isVisible(el)) {
                    result.buttons.push({
                        text: getCleanText(el),
                        selector: buildSelector(el),
                        type: el.type || 'button'
                    });
                }
            });
            
            // Collect links
            document.querySelectorAll('a[href]').forEach(el => {
                if (isVisible(el)) {
                    result.links.push({
                        text: getCleanText(el),
                        selector: buildSelector(el),
                        href: el.href
                    });
                }
            });
            
            // Collect inputs
            document.querySelectorAll('input:not([type="button"]):not([type="submit"]), textarea').forEach(el => {
                if (isVisible(el)) {
                    result.inputs.push({
                        text: getCleanText(el),
                        selector: buildSelector(el),
                        type: el.type || 'text',
                        placeholder: el.placeholder || ''
                    });
                }
            });
            
            // Collect selects
            document.querySelectorAll('select').forEach(el => {
                if (isVisible(el)) {
                    const options = Array.from(el.options).slice(0, 5).map(opt => opt.text.trim());
                    result.selects.push({
                        text: getCleanText(el),
                        selector: buildSelector(el),
                        options: options
                    });
                }
            });
            
            // Collect other interactive elements
            document.querySelectorAll('[onclick], [role="search"], [role="textbox"]').forEach(el => {
                if (isVisible(el) && !el.closest('button, a, input, textarea, select')) {
                    result.other.push({
                        text: getCleanText(el),
                        selector: buildSelector(el),
                        role: el.getAttribute('role') || 'interactive'
                    });
                }
            });
            
            return result;
        }
        """
        
        elements = browser_state.page.evaluate(dom_script)
        
        # Build readable output
        output = []
        output.append(f"📄 Page: {browser_state.page.title()}")
        output.append(f"🔗 URL: {browser_state.page.url}")
        output.append("")
        
        # Count total elements
        total = (len(elements['buttons']) + len(elements['links']) + 
                len(elements['inputs']) + len(elements['selects']) + 
                len(elements['other']))
        
        output.append(f"Found {total} interactive elements")
        output.append("=" * 80)
        output.append("")
        
        count = 0
        max_reached = False
        
        # Buttons
        if elements['buttons']:
            output.append("🔘 BUTTONS:")
            for btn in elements['buttons']:
                if count >= max_elements:
                    max_reached = True
                    break
                count += 1
                text = btn['text'] if btn['text'] else '(no text)'
                output.append(f"  [{count}] \"{text}\"")
                output.append(f"      💡 Use: click(text=\"{text}\") or click(selector=\"{btn['selector']}\")")
                output.append("")
        
        # Links
        if not max_reached and elements['links']:
            output.append("🔗 LINKS:")
            for link in elements['links']:
                if count >= max_elements:
                    max_reached = True
                    break
                count += 1
                text = link['text'] if link['text'] else '(no text)'
                output.append(f"  [{count}] \"{text}\"")
                output.append(f"      → {link['href'][:60]}")
                output.append(f"      💡 Use: click(text=\"{text}\") or click(selector=\"{link['selector']}\")")
                output.append("")
        
        # Inputs
        if not max_reached and elements['inputs']:
            output.append("📝 INPUT FIELDS:")
            for inp in elements['inputs']:
                if count >= max_elements:
                    max_reached = True
                    break
                count += 1
                label = inp['placeholder'] or inp['text'] or '(no label)'
                output.append(f"  [{count}] {inp['type']}: {label}")
                
                # Provide multiple ways to target the input
                if inp['placeholder']:
                    ph_selector = f"{inp['type']}[placeholder=\"{inp['placeholder']}\"]"
                    output.append(f"      💡 Best: type_text(selector='{ph_selector}', text=\"...\")")
                    output.append(f"      💡 Alt:  type_text(selector=\"{inp['selector']}\", text=\"...\")")
                else:
                    output.append(f"      💡 Use: type_text(selector=\"{inp['selector']}\", text=\"...\")")
                output.append("")
        
        # Selects
        if not max_reached and elements['selects']:
            output.append("📋 DROPDOWNS:")
            for sel in elements['selects']:
                if count >= max_elements:
                    max_reached = True
                    break
                count += 1
                label = sel['text'] if sel['text'] else '(no label)'
                output.append(f"  [{count}] {label}")
                if sel['options']:
                    output.append(f"      Options: {', '.join(sel['options'][:3])}...")
                output.append(f"      💡 Use: click(selector=\"{sel['selector']}\")")
                output.append("")
        
        # Other interactive elements
        if not max_reached and elements['other']:
            output.append("⚡ OTHER INTERACTIVE:")
            for elem in elements['other']:
                if count >= max_elements:
                    max_reached = True
                    break
                count += 1
                text = elem['text'] if elem['text'] else '(no text)'
                output.append(f"  [{count}] {elem['role']}: {text}")
                output.append(f"      💡 Use: click(selector=\"{elem['selector']}\")")
                output.append("")
        
        if max_reached:
            remaining = total - max_elements
            output.append(f"... and {remaining} more elements (increase max_elements to see more)")
        
        return "\n".join(output)
    
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
        content = browser_state.page.evaluate("() => document.body.innerText")
        return content[:10000]
    except Exception as e:
        return f"❌ Failed to get page content: {str(e)}"
