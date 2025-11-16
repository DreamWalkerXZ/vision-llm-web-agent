from bs4 import BeautifulSoup
import json
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

class SemanticDOMAnalyzer:
    def __init__(self):
        self.interactive_roles = {
            'button', 'menuitemradio', 'menuitemcheckbox', 'radio', 'checkbox',
            'tab', 'switch', 'slider', 'spinbutton', 'combobox',
            'searchbox', 'textbox', 'option', 'scrollbar'
        }

    def extract_dom_from_page(self, page):
        """直接从 playwright 的 page 提取交互元素（包含位置信息）"""
        # 使用 JavaScript 获取可见元素及其位置
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
                    
                    // 获取所有属性
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
        
        # 执行 JavaScript 获取元素信息
        raw_elements = page.evaluate(js_script)
        
        # 确保返回的是列表
        if not isinstance(raw_elements, list):
            print(f"⚠️  JavaScript returned unexpected type: {type(raw_elements)}")
            return []
        
        # 为每个元素添加语义分析
        elements = []
        for el_data in raw_elements:
            try:
                # 验证元素数据结构
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
        """判断是否为交互元素（已弃用，保留用于兼容性）"""
        if role in self.interactive_roles:
            return True
        if tag in ["button", "a", "input", "select", "textarea", "label"]:
            return True
        # Note: el.attrs checks removed since we now use JavaScript evaluation
        return False

    def analyze_semantic_from_data(self, tag, text, attrs, role):
        """从数据字典进行启发式语义分类"""
        lower_text = text.lower()
        class_value = attrs.get("class", "")
        if isinstance(class_value, list):
            class_str = " ".join(class_value).lower()
        else:
            class_str = str(class_value).lower()

        if any(k in class_str for k in ["video", "player", "media"]) or tag == "video":
            return {"type": "video_content", "hint": "🎬 点击观看视频"}
        if any(k in lower_text for k in ["播放", "play", "▶", "►"]) or "play" in class_str:
            return {"type": "play_button", "hint": "▶️ 点击播放"}
        if "search" in class_str or "搜索" in lower_text or attrs.get("type") == "search":
            return {"type": "search_input", "hint": "🔍 输入搜索内容"}
        if any(k in lower_text for k in ["提交", "submit", "send"]):
            return {"type": "submit_button", "hint": "✅ 提交表单"}
        if any(k in lower_text for k in ["下载", "download", "保存"]):
            return {"type": "download_button", "hint": "⬇️ 下载文件"}
        if any(k in lower_text for k in ["广告", "ad", "sponsor"]):
            return {"type": "advertisement", "hint": "⚠️ 广告内容"}
        if tag == "a" or role == "navigation":
            return {"type": "navigation_link", "hint": "🧭 点击导航"}
        return {"type": "unknown", "hint": f"🎯 与 {tag} 交互"}
    
    def analyze_semantic(self, el, tag, text, attrs, role):
        """启发式语义分类（保留用于兼容性）"""
        return self.analyze_semantic_from_data(tag, text, attrs, role)
    
    def filter_interactive_elements(self, client, elements, user_prompt, model='qwen-flash', max_elements=20):
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
        system_prompt = f"你是一个html元素筛选器，为下游的web agent筛选有用的html元素，比如搜索框元素，点击后搜索播放等交互元素。注意，一些带有nav/search性质的div元素也需要保留。用户将输入一个问题，以及一系列结构化的元素。请根据问题，筛选出与问题最相关的'max = {max_elements}'元素，并返回这些元素的编号列表。你只需要返回编号列表，格式为：```json [1,3,5]```，不要返回其他内容。"
        for tag in input_elements:
            if(len(input_elements[tag])<=max_elements):
                print(f"✅ 选择了元素 [{tag}] 数量 {len(input_elements[tag])}")
                filtered_elements.extend(all_elements[tag])
                continue
            input_prompt = "\n".join(input_elements[tag])
            message = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n\n以下是页面上的<{tag}>元素：\n{input_prompt}"}
            ]
            response = client.chat.completions.create(
                model=model,
                messages=message,
                temperature=0.7,
                max_tokens=200,
            )
            # 使用re 解析编号列表```json [1,3,5]```
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
                            print(f"✅ 选择了元素 [{tag}] 编号 {num}")
                except Exception as e:
                    print(f"解析编号列表失败: {e}")
        
        return filtered_elements

    def to_llm_representation(self, elements, max_elements=5):
        """转为 LLM 可读文本（同时保留位置信息）"""
        lines = []
        elements_count = {el['tag']: 0 for el in elements}
        count = 0
        filtered_elements = []  # 保存被选中的元素（包含位置信息）
        
        for i, el in enumerate(elements):
            if elements_count[el['tag']] >= max_elements:
                continue
            count += 1
            elements_count[el['tag']] += 1
            
            # 添加到过滤后的元素列表
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
                
            # hint = f" → {el['semantic']['hint']}"
            if el['tag'] in ['textarea', 'input', 'textbox']:
                tool_call = f" tool_call: type_text {{selector: '{selector}, text: '<text_to_type>'}}"
            else:
                tool_call = f" tool_call: click {{selector:  '{selector}'}}"
                
            lines.append(desc + tool_call)
        
        return "\n".join(lines), filtered_elements

    def analyze_page(self, page, client, user_prompt, model='qwen-flash', max_elements=20):
        """主入口：分析已有 page 对象"""
        elements = self.extract_dom_from_page(page)
        if model is None or model == '':
            filtered_elements = elements
        else:
            filtered_elements = self.filter_interactive_elements(client, elements, user_prompt=user_prompt, model=model, max_elements=max_elements)
            
        text_repr, filtered_elements = self.to_llm_representation(filtered_elements, max_elements=max_elements)
        return {
            "elements": elements,
            "llm_text": text_repr,
            "filtered_elements": filtered_elements  # 包含序号和位置的过滤元素
        }
    
    def annotate_screenshot(self, screenshot_path: str, filtered_elements: list, output_path: Optional[str] = None) -> str:
        """
        在截图上标注元素序号
        
        Args:
            screenshot_path: 原始截图路径
            filtered_elements: 过滤后的元素列表（包含index和element）
            output_path: 输出路径，如果为None则覆盖原文件
        
        Returns:
            标注后的截图路径
        """
        try:
            # 打开截图
            img = Image.open(screenshot_path)
            draw = ImageDraw.Draw(img)
            
            # 尝试加载字体，如果失败则使用默认字体
            try:
                # Windows 系统字体
                font = ImageFont.truetype("arial.ttf", 16)
                font_large = ImageFont.truetype("arial.ttf", 20)
            except:
                try:
                    # 备选字体
                    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
                    font_large = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
                except:
                    # 使用默认字体
                    font = ImageFont.load_default()
                    font_large = ImageFont.load_default()
            
            # 为每个元素绘制标注
            for item in filtered_elements:
                index = item["index"]
                el = item["element"]
                bbox = el["bbox"]
                
                # 计算标签位置（元素中心点）
                center_x = bbox["centerX"]
                center_y = bbox["centerY"]
                
                # 绘制半透明背景圆圈
                label_text = str(index)
                
                # 计算文本边界框以确定圆圈大小
                # 使用 textbbox 获取文本边界
                bbox_text = draw.textbbox((0, 0), label_text, font=font_large)
                text_width = bbox_text[2] - bbox_text[0]
                text_height = bbox_text[3] - bbox_text[1]
                
                # 圆圈半径（稍大于文本）
                radius = max(text_width, text_height) // 2 + 8
                
                # 绘制半透明红色圆圈（通过多次绘制实现半透明效果）
                circle_bbox = [
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius
                ]
                
                # 绘制外圈（红色边框）
                draw.ellipse(circle_bbox, fill=(255, 0, 0, 180), outline=(255, 0, 0), width=2)
                
                # 绘制文本（白色）
                # 计算文本位置使其居中
                text_x = center_x - text_width // 2
                text_y = center_y - text_height // 2
                draw.text((text_x, text_y), label_text, fill=(255, 255, 255), font=font_large)
                
                # 可选：绘制边界框（用于调试）
                # draw.rectangle(
                #     [bbox["x"], bbox["y"], bbox["x"] + bbox["width"], bbox["y"] + bbox["height"]],
                #     outline=(0, 255, 0), width=1
                # )
            
            # 保存标注后的截图
            if output_path is None:
                output_path = screenshot_path
            
            img.save(output_path)
            return f"✅ Screenshot annotated with {len(filtered_elements)} labels: {output_path}"
            
        except Exception as e:
            print(f"❌ analyze_page error: {str(e)}")
            import traceback
            traceback.print_exc()
            # 返回空结果而不是抛出异常
            return {
                "elements": [],
                "llm_text": f"Error analyzing page: {str(e)}",
                "filtered_elements": []
            }

semantic_dom_analyzer = SemanticDOMAnalyzer()