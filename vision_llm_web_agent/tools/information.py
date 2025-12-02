"""
Information Gathering Tools
Tools for capturing screenshots, DOM, and page content
"""

from pathlib import Path
from .base import tool
from .browser_control import browser_state
from .dom_analyzer import semantic_dom_analyzer
from ..config.settings import ARTIFACTS_DIR, get_session_artifacts_dir


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
        # Normalize path to session artifacts_dir/filename (single level)
        session_artifacts_dir = get_session_artifacts_dir()
        save_path_obj = Path(file_name)
        if not save_path_obj.is_absolute():
            # Extract filename and use session artifacts_dir
            filename = save_path_obj.name
            save_path_obj = session_artifacts_dir / filename
        save_path = str(save_path_obj)
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        # Use get_current_page() to handle multi-tab scenarios
        page = browser_state.get_current_page()
        if not page:
            return "❌ No active page found"
        page.screenshot(path=save_path, full_page=False)
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
        # Use get_current_page() to handle multi-tab scenarios
        page = browser_state.get_current_page()
        if not page:
            return "❌ No active page found"
        
        # Wait for page to be fully loaded (especially for dynamic content)
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        # If networkidle times out, that's okay - continue with current state
        pass
    
    try:
        # JavaScript to extract interactive elements with better organization
        dom_script = """
        () => {
            const result = {
                buttons: [],
                links: [],
                inputs: [],
                selects: [],
                forms: [],
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
                        type: el.type || 'button',
                        disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
                        formId: el.form ? (el.form.id || el.form.name || '') : ''
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
            
            // Collect inputs (prioritize search inputs)
            // Try multiple strategies to find inputs, including those that might be in shadow DOM or iframes
            const inputSelectors = [
                'input:not([type="button"]):not([type="submit"]):not([type="hidden"]):not([type="checkbox"]):not([type="radio"])',
                'textarea',
                'input[type="search"]',
                'input[type="text"]',
                '[contenteditable="true"]'
            ];
            
            inputSelectors.forEach(selector => {
                try {
                    document.querySelectorAll(selector).forEach(el => {
                        // Check if already added
                        const alreadyAdded = result.inputs.some(inp => {
                            const elId = el.id || '';
                            const elName = el.name || '';
                            return (inp.id === elId && elId) || (inp.name === elName && elName);
                        });
                        if (!alreadyAdded && isVisible(el)) {
                            const form = el.form || el.closest('form');
                            result.inputs.push({
                                text: getCleanText(el),
                                selector: buildSelector(el),
                                type: el.type || el.tagName.toLowerCase(),
                                placeholder: el.placeholder || '',
                                name: el.name || '',
                                id: el.id || '',
                                ariaLabel: el.getAttribute('aria-label') || '',
                                inForm: !!form,
                                formId: form ? (form.id || form.name || '') : '',
                                formAction: form ? (form.action || '') : ''
                            });
                        }
                    });
                } catch (e) {
                    // Continue if selector fails
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
            
            // Collect forms
            document.querySelectorAll('form').forEach(form => {
                if (isVisible(form)) {
                    const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
                    const inputs = Array.from(form.querySelectorAll('input:not([type="hidden"]), textarea, select'));
                    result.forms.push({
                        id: form.id || form.name || '',
                        action: form.action || '',
                        method: form.method || 'get',
                        hasSubmitButton: !!submitButton,
                        submitButtonText: submitButton ? getCleanText(submitButton) : '',
                        inputCount: inputs.length,
                        visibleInputs: inputs.filter(inp => isVisible(inp)).length
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
        
        elements = page.evaluate(dom_script)
        
        # Build readable output
        output = []
        output.append(f"📄 Page: {page.title()}")
        current_url = page.url
        output.append(f"🔗 URL: {current_url}")
        output.append("")
        
        # Detect if current page is a PDF
        is_pdf_page = False
        pdf_url = None
        try:
            # Check URL for PDF indicators
            if current_url.lower().endswith('.pdf') or '/pdf' in current_url.lower() or 'application/pdf' in current_url.lower():
                is_pdf_page = True
                pdf_url = current_url
            else:
                # Check content-type via JavaScript
                content_type = page.evaluate("""() => {
                    try {
                        const meta = document.querySelector('meta[http-equiv="Content-Type"]');
                        if (meta) return meta.content;
                        // Check if page is actually a PDF viewer
                        if (document.body && document.body.innerHTML.includes('%PDF')) return 'application/pdf';
                        return null;
                    } catch(e) { return null; }
                }""")
                if content_type and 'pdf' in content_type.lower():
                    is_pdf_page = True
                    pdf_url = current_url
        except Exception:
            pass
        
        # If PDF detected, add prominent warning
        if is_pdf_page:
            output.append("=" * 80)
            output.append("🚨 PDF PAGE DETECTED - IMPORTANT:")
            output.append("=" * 80)
            output.append(f"⚠️  The current page appears to be a PDF file!")
            output.append(f"📄 PDF URL: {pdf_url}")
            output.append("")
            output.append("💡 ACTION REQUIRED:")
            output.append("   You MUST download this PDF using the download_pdf tool:")
            output.append(f"   download_pdf(url=\"{pdf_url}\", file_name=\"report.pdf\")")
            output.append("")
            output.append("⚠️  DO NOT try to scroll or interact with the PDF in the browser!")
            output.append("⚠️  DO NOT try to extract text/images from the browser PDF viewer!")
            output.append("⚠️  You MUST download it first, then use pdf_extract_text/pdf_extract_images tools!")
            output.append("=" * 80)
            output.append("")
        
        # Count total elements
        total = (len(elements['buttons']) + len(elements['links']) + 
                len(elements['inputs']) + len(elements['selects']) + 
                len(elements['forms']) + len(elements['other']))
        
        output.append(f"Found {total} interactive elements")
        output.append("=" * 80)
        output.append("")
        
        # IMPORTANT: Always show INPUT FIELDS first if they exist, even if we need to truncate other sections
        # This ensures VLLM can always find input selectors
        
        count = 0
        max_reached = False
        
        # CRITICAL: Show INPUT FIELDS FIRST (before forms/buttons) so VLLM can always find selectors
        # Inputs (prioritize search inputs) - Show these FIRST if they exist
        if elements['inputs']:
            # Sort inputs to prioritize search inputs
            sorted_inputs = sorted(elements['inputs'], key=lambda x: (
                'search' not in (x.get('name', '') + x.get('placeholder', '') + x.get('id', '')).lower(),
                x.get('name', '') != 'q'
            ))
            
            # Always show INPUT FIELDS section, even if we need to skip other sections
            output.append("📝 INPUT FIELDS:")
            inputs_shown = 0
            max_inputs_to_show = min(10, len(sorted_inputs))  # Show up to 10 inputs
            for inp in sorted_inputs:
                if inputs_shown >= max_inputs_to_show:
                    break
                inputs_shown += 1
                label = inp.get('placeholder') or inp.get('text') or inp.get('name') or inp.get('id') or inp.get('ariaLabel') or '(no label)'
                input_type = inp.get('type', 'text')
                output.append(f"  [{inputs_shown}] {input_type}: {label}")
                
                # Provide multiple ways to target the input
                # For search inputs, emphasize using type_text directly
                is_search = ('search' in label.lower() or 
                            inp.get('name') == 'q' or 
                            'search' in inp.get('selector', '').lower() or
                            inp.get('id') == 'search' or
                            'query' in label.lower())
                if is_search:
                    output.append(f"      ⚠️  SEARCH INPUT - Use type_text directly, NO need to click first!")
                
                # Build selector with priority: id > name > placeholder > type > selector
                # Try multiple selector strategies
                selectors_to_try = []
                if inp.get('id'):
                    selectors_to_try.append(f"#{inp['id']}")
                    selectors_to_try.append(f"input#{inp['id']}")
                if inp.get('name'):
                    selectors_to_try.append(f"input[name=\"{inp['name']}\"]")
                    selectors_to_try.append(f"{input_type}[name=\"{inp['name']}\"]")
                if inp.get('placeholder'):
                    selectors_to_try.append(f"input[placeholder=\"{inp['placeholder']}\"]")
                    selectors_to_try.append(f"{input_type}[placeholder=\"{inp['placeholder']}\"]")
                if input_type and input_type != 'text':
                    selectors_to_try.append(f"input[type=\"{input_type}\"]")
                if inp.get('selector'):
                    selectors_to_try.append(inp.get('selector'))
                
                # Remove duplicates while preserving order
                seen = set()
                unique_selectors = []
                for sel in selectors_to_try:
                    if sel and sel not in seen:
                        seen.add(sel)
                        unique_selectors.append(sel)
                
                best_selector = unique_selectors[0] if unique_selectors else ''
                alt_selectors = unique_selectors[1:3] if len(unique_selectors) > 1 else []
                
                if best_selector:
                    # Check if input is in a form
                    if inp.get('inForm'):
                        form_info = f" (in form: {inp.get('formId', 'unnamed')})"
                        output.append(f"      📋 Form input{form_info}")
                        output.append(f"      💡 PRIMARY: type_text(selector=\"{best_selector}\", text=\"your query\") then press_key(\"Enter\")")
                        if alt_selectors:
                            output.append(f"      💡 ALTERNATIVE: type_text(selector=\"{alt_selectors[0]}\", text=\"your query\")")
                    else:
                        output.append(f"      💡 PRIMARY: type_text(selector=\"{best_selector}\", text=\"your query\") then press_key(\"Enter\")")
                        if alt_selectors:
                            output.append(f"      💡 ALTERNATIVE: type_text(selector=\"{alt_selectors[0]}\", text=\"your query\")")
                output.append("")
        
        # Forms - Show after inputs (important for form submission)
        if elements['forms']:
            output.append("📋 FORMS:")
            for form in elements['forms']:
                if count >= max_elements:
                    max_reached = True
                    break
                count += 1
                form_id = form.get('id') or form.get('action', '').split('/')[-1] or 'form'
                output.append(f"  [{count}] Form: {form_id}")
                output.append(f"      Method: {form.get('method', 'get').upper()}")
                output.append(f"      Inputs: {form.get('visibleInputs', 0)} visible")
                if form.get('hasSubmitButton'):
                    output.append(f"      Submit button: \"{form.get('submitButtonText', 'Submit')}\"")
                    output.append(f"      💡 Method 1: Click submit button: click(text=\"{form.get('submitButtonText', 'Submit')}\")")
                else:
                    output.append(f"      ⚠️  No submit button found")
                output.append(f"      💡 Method 2: After typing in input, use press_key(\"Enter\") to submit form")
                output.append(f"      💡 Method 3: Find submit button in BUTTONS section below")
                output.append("")
        
        # Buttons
        if elements['buttons']:
            output.append("🔘 BUTTONS:")
            for btn in elements['buttons']:
                if count >= max_elements:
                    max_reached = True
                    break
                count += 1
                text = btn['text'] if btn['text'] else '(no text)'
                disabled = btn.get('disabled', False)
                if disabled:
                    output.append(f"  [{count}] \"{text}\" ⚠️ DISABLED")
                else:
                    output.append(f"  [{count}] \"{text}\"")
                output.append(f"      💡 Use: click(text=\"{text}\") or click(selector=\"{btn['selector']}\")")
                if btn.get('formId'):
                    output.append(f"      📋 Part of form: {btn['formId']}")
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
        
        # Inputs section already shown above (moved to top)
        
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
        # Use get_current_page() to handle multi-tab scenarios
        page = browser_state.get_current_page()
        if not page:
            return "❌ No active page found"
        content = page.evaluate("() => document.body.innerText")
        return content[:10000]
    except Exception as e:
        return f"❌ Failed to get page content: {str(e)}"
