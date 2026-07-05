import os


from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

@tool
def add(a: int, b: int) -> int:
    """计算并返回两个整数的和。"""
    return a + b

model = ChatOpenAI(
    model="z-ai/glm-5.1",
    base_url="https://ai.hybgzs.com/v1",
    api_key=os.environ["LLM_API_KEY"],
    timeout=30,
)

agent = create_agent(
    model = model,
    tools = [add],
    system_prompt="你是数学助手。遇到两个整数相加时，必须使用add工具。"
)

result = agent.invoke(
    {
        "messages":[
            {"role":"user", "content": "你好,先介绍一下你自己"}
        ]
    }
)

for message in result["messages"]:
    print(f"\n消息类型: {type(message).__name__}")
    print("消息内容：", message.content)

    if getattr(message, "tool_calls", None):
        print("工具调用：", message.tool_calls)
