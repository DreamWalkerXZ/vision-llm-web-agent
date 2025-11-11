from bs4 import BeautifulSoup
import json

class SemanticDOMAnalyzer:
    def __init__(self):
        self.interactive_roles = {
            'button', 'menuitemradio', 'menuitemcheckbox', 'radio', 'checkbox',
            'tab', 'switch', 'slider', 'spinbutton', 'combobox',
            'searchbox', 'textbox', 'option', 'scrollbar'
        }

    def extract_dom_from_page(self, page):
        """直接从 playwright 的 page 提取交互元素"""
        html = page.content()  # 同步获取完整 DOM
        soup = BeautifulSoup(html, 'html.parser')
        elements = []

        for el in soup.find_all(True):  # 遍历所有标签
            tag = el.name
            text = el.get_text(strip=True)[:80]
            attrs = {k: v for k, v in el.attrs.items() if isinstance(v, (str, list))}
            role = el.attrs.get("role", "").lower()

            # 判断是否为交互元素
            if self.is_interactive(el, tag, role):
                elements.append({
                    "tag": tag,
                    "text": text,
                    "attributes": attrs,
                    "role": role,
                    "semantic": self.analyze_semantic(el, tag, text, attrs, role)
                })

        return elements

    def is_interactive(self, el, tag, role):
        """判断是否为交互元素"""
        if role in self.interactive_roles:
            return True
        if tag in ["button", "a", "input", "select", "textarea", "label"]:
            return True
        if any(k in el.attrs for k in ["onclick", "onchange", "oninput"]):
            return True
        if "cursor: pointer" in str(el.attrs.get("style", "")):
            return True
        return False

    def analyze_semantic(self, el, tag, text, attrs, role):
        """启发式语义分类"""
        lower_text = text.lower()
        class_str = " ".join(attrs.get("class", [])).lower() if "class" in attrs else ""

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

    def to_llm_representation(self, elements):
        """转为 LLM 可读文本"""
        lines = []
        for i, el in enumerate(elements, 1):
            desc = f"[{i}] <{el['tag']}> ({el['semantic']['type']}) {el['text'][:50]}"
            hint = f" → {el['semantic']['hint']}"
            lines.append(desc + hint)
        return "\n".join(lines)

    def analyze_page(self, page):
        """主入口：分析已有 page 对象"""
        elements = self.extract_dom_from_page(page)
        text_repr = self.to_llm_representation(elements)
        return {
            "elements": elements,
            "llm_text": text_repr
        }

semantic_dom_analyzer = SemanticDOMAnalyzer()