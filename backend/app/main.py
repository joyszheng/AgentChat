from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from uuid import uuid4

from . import models
from .database import engine
from .routers import tasks, ai


# 开发阶段启动时自动建表；生产环境建议改用数据库迁移工具。
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# 允许本地前端开发服务器访问 API。
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 添加跨域中间件，使前端能携带凭据调用后端接口。
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 将任务相关路由注册到主应用。
app.include_router(ai.router)
app.include_router(tasks.router)


@app.get("/")
def read_root():
    """提供最小的服务存活检查接口。"""

    return {"Hello": "World"}

# 统一保存上传文件，并在首次启动时自动创建目录。
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """保存上传文件，并返回服务端生成的安全文件名。"""

    content = await file.read()

    suffix = Path(file.filename).suffix
    new_filename = f"{uuid4().hex}{suffix}"
    file_path = UPLOAD_DIR / new_filename

    with open(file_path, "wb") as f:
        f.write(content)

    return {
        "filename": new_filename,
        "content_type": file.content_type,
        "size": len(content),
        "saved_to": str(file_path),
        "message": "文件上传成功"
    }
