from bs4 import BeautifulSoup
import json
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

class SemanticDOMAnalyzer:
    """Enhanced DOM analyzer with semantic classification and screenshot annotation"""
    
    def __init__(self):
        self.interactive_roles = {
            'button', 'menuitemradio', 'menuitemcheckbox', 'radio', 'checkbox',
            'tab', 'switch', 'slider', 'spinbutton', 'combobox',
            'searchbox', 'textbox', 'option', 'scrollbar'
        }

    def extract_dom_from_page(self, page):
        """Extract interactive elements from a Playwright page (includes position data)."""
        # Use JavaScript to capture visible elements and their positions
        js_script = """
        () => {
            const elements = [];
            const allElements = document.querySelectorAll('*');
            
            const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && 
                       rect.height > 0 && 
                       style.display !== 'none' && 
                       style.visibility !== 'hidden' &&
                       style.opacity !== '0';
            };
            
            const isInteractive = (el) => {
                const tag = el.tagName.toLowerCase();
                const role = (el.getAttribute('role') || '').toLowerCase();
                const style = window.getComputedStyle(el);
                const interactiveRoles = ['button', 'menuitemradio', 'menuitemcheckbox', 
                    'radio', 'checkbox', 'tab', 'switch', 'slider', 'spinbutton', 
                    'combobox', 'searchbox', 'textbox', 'option', 'scrollbar'];
                const interactiveTags = ['button', 'a', 'input', 'select', 'textarea', 'label'];
                
                if (interactiveRoles.includes(role)) return true;
                if (interactiveTags.includes(tag)) return true;
                if (el.onclick || el.onchange || el.oninput) return true;
                if (style && style.cursor === 'pointer') return true;
                return false;
            };
            const excludedTags = ['svg', 'path', 'picture', 'img'];
            allElements.forEach((el, index) => {
                if (isVisible(el) && isInteractive(el) && !excludedTags.includes(el.tagName.toLowerCase())) {
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || el.textContent || el.value || 
                                el.placeholder || el.alt || el.title || '').trim().substring(0, 80);
                    const tag = el.tagName.toLowerCase();
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    
                    // Collect all attributes
                    const attrs = {};
                    for (let attr of el.attributes) {
                        attrs[attr.name] = attr.value;
                    }
                    
                    elements.push({
                        tag: tag,
                        text: text,
                        attributes: attrs,
                        role: role,
                        bbox: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            centerX: Math.round(rect.x + rect.width / 2),
                            centerY: Math.round(rect.y + rect.height / 2)
                        }
                    });
                }
            });
            
            return elements;
        }
        """
        
        # Execute JavaScript in the page to capture element metadata
        raw_elements = page.evaluate(js_script)
        
        # Ensure the returned value is a list
        if not isinstance(raw_elements, list):
            print(f"⚠️  JavaScript returned unexpected type: {type(raw_elements)}")
            return []
        
        # Attach semantic annotations to each element
        elements = []
        for el_data in raw_elements:
            try:
                # Validate the structure of the element data
                if not isinstance(el_data, dict):
                    print(f"⚠️  Element data is not a dict: {type(el_data)}")
                    continue
                
                semantic = self.analyze_semantic_from_data(
                    el_data.get('tag', ''), 
                    el_data.get('text', ''), 
                    el_data.get('attributes', {}), 
                    el_data.get('role', '')
                )
                elements.append({
                    "tag": el_data.get('tag', ''),
                    "text": el_data.get('text', ''),
                    "attributes": el_data.get('attributes', {}),
                    "role": el_data.get('role', ''),
                    "bbox": el_data.get('bbox', {}),
                    "semantic": semantic
                })
            except Exception as e:
                print(f"⚠️  Error processing element: {e}")
                continue
        
        return elements

    def is_interactive(self, el, tag, role):
        """Determine if an element is interactive (deprecated, kept for compatibility)."""
        if role in self.interactive_roles:
            return True
        if tag in ["button", "a", "input", "select", "textarea", "label"]:
            return True
        return False

    def analyze_semantic_from_data(self, tag, text, attrs, role):
        """Perform heuristic semantic classification from a data dictionary."""
        lower_text = text.lower()
        class_value = attrs.get("class", "")
        if isinstance(class_value, list):
            class_str = " ".join(class_value).lower()
        else:
            class_str = str(class_value).lower()

        if any(k in class_str for k in ["video", "player", "media"]) or tag == "video":
            return {"type": "video_content", "hint": "🎬 Click to watch the video"}
        if any(k in lower_text for k in ["play", "▶", "►"]) or "play" in class_str:
            return {"type": "play_button", "hint": "▶️ Click to play"}
        if "search" in class_str or attrs.get("type") == "search":
            return {"type": "search_input", "hint": "🔍 Enter search terms"}
        if any(k in lower_text for k in ["submit", "send"]):
            return {"type": "submit_button", "hint": "✅ Submit the form"}
        if any(k in lower_text for k in ["download", "save"]):
            return {"type": "download_button", "hint": "⬇️ Download the file"}
        if any(k in lower_text for k in ["ad", "advertisement", "sponsor"]):
            return {"type": "advertisement", "hint": "⚠️ Sponsored content"}
        if tag == "a" or role == "navigation":
            return {"type": "navigation_link", "hint": "🧭 Click to navigate"}
        return {"type": "unknown", "hint": f"🎯 Interact with {tag}"}
    
    def analyze_semantic(self, el, tag, text, attrs, role):
        """Heuristic semantic classification (compatibility wrapper)."""
        return self.analyze_semantic_from_data(tag, text, attrs, role)
    
    def filter_interactive_elements(self, client, elements, user_prompt, model='qwen-flash', max_elements=20):
        """Filter elements using LLM (optional enhancement)"""
        input_elements = {el['tag']: [] for el in elements}
        all_elements = {el['tag']: [] for el in elements}
        for idx, el in enumerate(elements):
            text = el['text'].strip() if el['text'] else "<no text>"
            count = len(input_elements[el['tag']])
            desc = f"[{count}] <{el['tag']}> ({el['semantic']['type']}) {text}"
            if el['attributes'].get("class"):
                if any(c in el['attributes']['class'] for c in ['nav', 'input', 'btn', 'menu', 'link', 'button']):
                    desc += f" [class: {el['attributes']['class']}]"
            hint = f" → {el['semantic']['hint']}"
            tool_call = f"tool_call: click {{text:  '{text}'}}"
            input_elements[el['tag']].append(f"{desc}{hint} {tool_call}")
            all_elements[el['tag']].append(el)
        
        filtered_elements = []
        system_prompt = (
            "You are an HTML element filter helping a downstream web agent. Share only the "
            "most relevant interactive elements such as search inputs, navigation links, "
            "and buttons. Keep div elements with nav/search semantics when useful. The user "
            "will provide a question and a structured element list. Return the indexes of up "
            f"to max = {max_elements} elements in the format ```json [1,3,5]``` and nothing else."
        )
        for tag in input_elements:
            if(len(input_elements[tag])<=max_elements):
                filtered_elements.extend(all_elements[tag])
                continue
            input_prompt = "\n".join(input_elements[tag])
            message = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n\nHere are the <{tag}> elements on the page:\n{input_prompt}"}
            ]
            response = client.chat.completions.create(
                model=model,
                messages=message,
                temperature=0.7,
                max_tokens=200,
            )
            # Use regex to parse an index list formatted as ```json [1,3,5]```
            import re
            match = re.search(r'```json\s*(\[[\d,\s]*\])\s*```', response.choices[0].message.content)
            if match:
                num_list_str = match.group(1)
                try:
                    num_list = eval(num_list_str)
                    elems = input_elements[tag]
                    for num in num_list:
                        if 0 <= num < len(elems):
                            filtered_elements.append(all_elements[tag][num])
                except Exception as e:
                    print(f"Failed to parse index list: {e}")
        
        return filtered_elements

    def to_llm_representation(self, elements, max_elements=5):
        """Convert to an LLM-readable text format while preserving position data."""
        lines = []
        elements_count = {el['tag']: 0 for el in elements}
        count = 0
        filtered_elements = []  # Store selected elements (with bounding boxes)
        
        for i, el in enumerate(elements):
            if elements_count[el['tag']] >= max_elements:
                continue
            count += 1
            elements_count[el['tag']] += 1
            
            # Track the element in the filtered list
            filtered_elements.append({
                "index": count,
                "element": el
            })
            text = el['text'].strip() if el['text'] else "<no text>"
            
            desc = f"[{count}] <{el['tag']}> ({el['semantic']['type']}) {text}"
            selector = ''
            if el['attributes'].get('id'):
                selector = f"#{el['attributes']['id']}"
            elif el['attributes'].get('name'):
                selector = f"[name='{el['attributes']['name']}']"
            elif el['attributes'].get('class') and el['attributes']['class'].split():
                class_name = el['attributes']['class'].strip()
                selector = "." + ".".join(class_name.split())
            else:
                selector = el['tag']
                
            if el['tag'] in ['textarea', 'input', 'textbox']:
                tool_call = f" tool_call: type_text {{selector: '{selector}, text: '<text_to_type>'}}"
            else:
                tool_call = f" tool_call: click {{selector:  '{selector}'}}"
                
            lines.append(desc + tool_call)
        
        return "\n".join(lines), filtered_elements

    def analyze_page(self, page, client=None, user_prompt="", model=None, max_elements=20):
        """Main entry point: analyze an existing Playwright page object."""
        elements = self.extract_dom_from_page(page)
        if model is None or model == '' or client is None:
            filtered_elements = elements
        else:
            filtered_elements = self.filter_interactive_elements(client, elements, user_prompt=user_prompt, model=model, max_elements=max_elements)
            
        text_repr, filtered_elements = self.to_llm_representation(filtered_elements, max_elements=max_elements)
        return {
            "elements": elements,
            "llm_text": text_repr,
            "filtered_elements": filtered_elements  # Includes indexes and location data
        }
    
    def annotate_screenshot(self, screenshot_path: str, filtered_elements: list, output_path: Optional[str] = None) -> str:
        """
        Annotate a screenshot with element indexes.
        
        Args:
            screenshot_path: Path to the original screenshot file.
            filtered_elements: Filtered element list with index and element entries.
            output_path: Optional output path; overwrites the source file when None.
        
        Returns:
            Path to the annotated screenshot.
        """
        try:
            # Open the screenshot
            img = Image.open(screenshot_path)
            draw = ImageDraw.Draw(img)
            
            # Try to load a readable font and fall back to the default
            try:
                # Windows system font
                font = ImageFont.truetype("arial.ttf", 16)
                font_large = ImageFont.truetype("arial.ttf", 20)
            except:
                try:
                    # Alternate font path
                    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
                    font_large = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
                except:
                    # Use the default font
                    font = ImageFont.load_default()
                    font_large = ImageFont.load_default()
            
            # Draw annotations for each element
            for item in filtered_elements:
                index = item["index"]
                el = item["element"]
                bbox = el["bbox"]
                
                # Compute the label position (element center)
                center_x = bbox["centerX"]
                center_y = bbox["centerY"]
                
                # Draw a semi-transparent background circle
                label_text = str(index)
                
                # Derive the circle size from the text bounding box
                bbox_text = draw.textbbox((0, 0), label_text, font=font_large)
                text_width = bbox_text[2] - bbox_text[0]
                text_height = bbox_text[3] - bbox_text[1]
                
                # Circle radius slightly larger than the text
                radius = max(text_width, text_height) // 2 + 8
                
                # Draw a semi-transparent red circle
                circle_bbox = [
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius
                ]
                
                # Draw the outer red border
                draw.ellipse(circle_bbox, fill=(255, 0, 0, 180), outline=(255, 0, 0), width=2)
                
                # Draw the label text (white)
                text_x = center_x - text_width // 2
                text_y = center_y - text_height // 2
                draw.text((text_x, text_y), label_text, fill=(255, 255, 255), font=font_large)
            
            # Save the annotated screenshot
            if output_path is None:
                output_path = screenshot_path
            
            img.save(output_path)
            return f"✅ Screenshot annotated with {len(filtered_elements)} labels: {output_path}"
            
        except Exception as e:
            print(f"❌ annotate_screenshot error: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"❌ Failed to annotate screenshot: {str(e)}"

# Global instance
semantic_dom_analyzer = SemanticDOMAnalyzer()

