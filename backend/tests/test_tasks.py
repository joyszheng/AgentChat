from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_read_root():
    """根路径应能作为服务存活检查使用。"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello": "World"}


def test_create_task():
    """创建任务后应返回生成的 ID 和原始字段。"""
    response = client.post(
        "/tasks",
        json={
            "title": "测试任务",
            "description": "用TestClient创建的测试任务",
            "completed": False
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "测试任务"
    assert data["description"] == "用TestClient创建的测试任务"
    assert data["completed"] is False
    assert "id" in data  # 确认返回的数据中包含任务 ID。


def test_get_not_found_task():
    """查询不存在的任务应返回 404。"""

    response = client.get("/tasks/9999")  # 使用远大于测试数据量的 ID。
    assert response.status_code == 404
    assert response.json() == {"detail": "任务不存在"}
