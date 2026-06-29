import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from backend.app.ai.tools import create_task_by_ai, list_uncompleted_tasks

load_dotenv()

model = ChatOpenAI(
    model="z-ai/glm-5.1",
    base_url="https://ai.hybgzs.com/v1",
    api_key=os.environ["GLM_API_KEY"],
    timeout=30,
)

agent = create_agent(
    model = model,
    tools = [list_uncompleted_tasks, create_task_by_ai],
    system_prompt=(
        "你是任务管理助手。"
        "用户查询待办事项时，使用 list_uncompleted_tasks。"
        "用户明确要求创建任务时，使用 create_task_by_ai。"
        "用户意图不明确时不要创建任务，也不能编造数据库内容。"
    )
)

result = agent.invoke({
    "messages": [
        {
            "role": "user",
            "content": "查询前 5 条未完成任务"
        }
    ]
})

for message in result["messages"]:
    print(f"\n消息类型：{type(message).__name__}")
    print("消息内容：",message.content)

    if getattr(message, "tool_calls", None):
        print("工具调用：", message.tool_calls)

print("\n最终回答：")
print(result["messages"][-1].content)
