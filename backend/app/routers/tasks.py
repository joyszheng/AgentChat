from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"]
)


@router.post("", response_model=schemas.TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    """创建一条任务。"""
    return crud.create_task(db, task)


@router.get("", response_model=list[schemas.TaskResponse])
def list_tasks(
    completed: bool | None = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    db: Session = Depends(get_db)
):
    """查询任务列表，可按完成状态筛选并分页。"""
    return crud.list_tasks(db, completed=completed, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=schemas.TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """返回指定 ID 的任务。"""
    task = crud.get_task(db, task_id)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return task


@router.put("/{task_id}", response_model=schemas.TaskResponse)
def update_task(
    task_id: int,
    task_update: schemas.TaskCreate,
    db: Session = Depends(get_db)
):
    """使用完整数据替换指定任务。"""
    task = crud.update_task(db, task_id, task_update)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return task


@router.patch("/{task_id}", response_model=schemas.TaskResponse)
def partial_update_task(
    task_id: int,
    task_update: schemas.TaskUpdate,
    db: Session = Depends(get_db)
):
    """更新指定任务中请求体提供的字段。"""
    task = crud.partial_update_task(db, task_id, task_update)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除指定任务。"""
    task = crud.delete_task(db, task_id)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return None
