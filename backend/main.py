from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel, EmailStr, Field
from typing import Annotated



# 创建 FastAPI 应用实例，后续通过装饰器注册接口
app = FastAPI()



@app.get("/")
def read_root():
    # 项目的根路径，用于快速确认服务是否正常运行
    return {"Hello": "World"}

