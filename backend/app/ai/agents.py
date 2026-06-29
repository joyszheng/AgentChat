from langchain.agents import create_agent

from .models import llm
from .tools import create_task_by_ai, list_uncompleted_tasks


task_agent = create_agent(
    model=llm,
    tools=[
        list_uncompleted_tasks,
        create_task_by_ai,
    ],
    system_prompt=(
        "你是任务管理助手。"
        "用户查询待办事项时，使用 list_uncompleted_tasks。"
        "用户明确要求创建任务时，使用 create_task_by_ai。"
        "意图不明确时不要创建任务，也不能编造数据库内容。"
    ),
)