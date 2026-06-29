from backend.app.ai.tools import list_uncompleted_tasks

result = list_uncompleted_tasks.invoke({"limit": 10})
print(result)