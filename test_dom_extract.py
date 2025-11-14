import asyncio
from playwright.sync_api import sync_playwright
from vision_llm_web_agent.tools.dom_analyzer import semantic_dom_analyzer
from openai import OpenAI
OPENAI_API_KEY='sk-ac712e0af26440a48e21f3d9ec2a9a23'
OPENAI_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
OPENAI_MODEL='qwen-flash'

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 如果你想看页面，设为 False
        page = browser.new_page()
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        
        max_useful_num = 5
        min_useful_num = 1
        system_prompt = f"你是一个html元素筛选器，为下游的web agent筛选有用的html元素，比如搜索相关元素，点击交互元素等。用户将输入一个问题，以及一系列结构化的元素。请根据问题，筛选出与问题最相关的'max = {max_useful_num}, min = {min_useful_num}'元素，并返回这些元素的编号列表。你只需要返回编号列表，格式为：```json [1,3,5]```，不要返回其他内容。"
        user_prompt = "请打开bilibil，搜索关键字“人工智能”，并找出页面上所有与“人工智能”相关的链接和按钮。"
        # === 测试页面，可以改成你自己的URL ===
        page.goto("https://www.baidu.com")

        print("按 y 提取当前页面元素，按其他键退出。")
        user_input = input(">>> ").strip().lower()
        while user_input == "y":
            elements = semantic_dom_analyzer.extract_dom_from_page(page)
            print(f"✅ 提取到 {len(elements)} 个元素：\n")
            
            # for el in elements:
            #     print(f"[{el['tag']}] {el['text']} ")
            #     # if el["interactivity"]["events"]:
            #     #     print(f"  ⚙️ 事件属性: {el['interactivity']['events']}")
            #     if el["attributes"].get("href"):
            #         print(f"  🔗 链接: {el['attributes']['href']}")
            #     if el["attributes"].get("onclick"):
            #         print(f"  🖱️ 点击事件: {el['attributes']['onclick']}")
            #     if el['attributes'].get("class"):
            #         print(f"  🎨 类名: {el['attributes']['class']}")
            #     # print(f"  属性: {el['attributes']}\n")
            # 使用 OpenAI API 进行筛选
            input_elements = {el['tag']: [] for el in elements}
            print(input_elements.keys())
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
            for tag in input_elements:
                input_prompt = "\n".join(input_elements[tag])
                message = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{user_prompt}\n\n以下是页面上的<{tag}>元素：\n{input_prompt}"}
                ]
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=message,
                    temperature=0.2,
                    max_tokens=200,
                )
                print(f"模型返回：{response.choices[0].message.content}")
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
            
            for idx, el in enumerate(filtered_elements):
                text = el['text'].strip() if el['text'] else "<no text>"
                desc = f"[{idx}] <{el['tag']}> ({el['semantic']['type']}) {text}"
                if el['attributes'].get("class"):
                    if any(c in el['attributes']['class'] for c in ['nav', 'input', 'btn', 'menu', 'link', 'button']):
                        desc += f" [class: {el['attributes']['class']}]"
                hint = f" → {el['semantic']['hint']}"
                tool_call = f"tool_call: click {{text:  '{text}'}}"
                text = f"{desc}{hint} {tool_call}"
                print(text)

            user_input = input(">>> ").strip().lower()

        browser.close()

if __name__ == "__main__":
    main()