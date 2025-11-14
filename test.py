from browser_use.llm import ChatOpenAI
from browser_use import Agent
from dotenv import load_dotenv
load_dotenv()
import asyncio
llm = ChatOpenAI(
    model="qwen3-vl-8b-instruct",
    api_key="sk-ac712e0af26440a48e21f3d9ec2a9a23",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
async def main():
    agent = Agent(
        task="Compare the price of gpt-4o and DeepSeek-V3",
        llm=llm,
    )
    result = await agent.run()
    print(result)
asyncio.run(main())