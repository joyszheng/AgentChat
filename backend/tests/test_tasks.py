from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """为每个测试提供独立的内存数据库，避免修改本地开发数据。"""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        # 让测试客户端的不同线程共享同一个内存数据库连接。
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_read_root(client: TestClient):
    """根路径应能作为服务存活检查使用。"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello": "World"}


def test_create_task(client: TestClient):
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


def test_get_not_found_task(client: TestClient):
    """查询不存在的任务应返回 404。"""

    response = client.get("/tasks/9999")  # 使用远大于测试数据量的 ID。
    assert response.status_code == 404
    assert response.json() == {"detail": "任务不存在"}
