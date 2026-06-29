from backend.app.ai.tools import create_task_by_ai

result = create_task_by_ai.invoke({
    "title": "学习 langchain agent",
    "description": "完成第二天第五节练习"
})

print(result)