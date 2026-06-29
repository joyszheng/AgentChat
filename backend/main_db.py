from fastapi import FastAPI, status, HTTPException, Query, Depends
from sqlalchemy import create_engine, Boolean, String
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, Session
from pydantic import BaseModel, Field
from typing import Annotated

app = FastAPI()

DATABASE_URL = "sqlite:///./test.db"  # 使用 SQLite 数据库，数据库文件为 test.db
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})  # SQLite 特有参数，允许多线程访问

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

Base.metadata.create_all(bind=engine)  # 创建数据库表

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



@app.get("/")
def read_root():
    # 项目的根路径，用于快速确认服务是否正常运行
    return {"Hello": "World"}

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100, description="任务标题，最大长度为100个字符")
    description: str | None = Field(None, max_length=500, description="任务描述，最大长度为500个字符")
    completed: bool = False

class TaskResponse(TaskCreate):
    id: int
    
    model_config = {
        "from_attributes": True  # 允许从 ORM 模型实例创建 Pydantic 模型实例
    }

class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    completed: bool | None = None



@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    db_task = Task(
        title=task.title,
        description=task.description,
        completed=task.completed
    )

    db.add(db_task)
    db.commit()
    db.refresh(db_task)  # 刷新实例以获取数据库生成的 ID

    return db_task

@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    completed: bool | None = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    db: Session = Depends(get_db)
):
    query = db.query(Task)
    if completed is not None:
        query = query.filter(Task.completed == completed)
    
    return query.offset(skip).limit(limit).all()

@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task

@app.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    if task_update.title is not None:
        task.title = task_update.title
    if task_update.description is not None:
        task.description = task_update.description
    if task_update.completed is not None:
        task.completed = task_update.completed

    db.commit()
    db.refresh(task)

    return task


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def partial_update_task(task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    
    update_data = task_update.model_dump(exclude_unset=True)
    for key,value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)

    return task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    
    db.delete(task)
    db.commit()
    return None