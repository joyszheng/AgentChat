# AgentChat

AgentChat 是一个用于学习 FastAPI、SQLAlchemy 与 LangChain 的 AI 任务助手后端。

## 已实现功能

- 任务的创建、查询、更新和删除
- 普通 AI 聊天
- AI 查询未完成任务
- AI 创建任务
- 基于固定文档的 RAG 问答
- 文件上传
- pytest 接口与异常测试

## 项目结构

```text
AgentChat/
├─ backend/
│  ├─ app/
│  │  ├─ ai/
│  │  │  ├─ models.py      # LLM 初始化
│  │  │  ├─ prompts.py     # Prompt 模板
│  │  │  ├─ chains.py      # Chain 组装
│  │  │  ├─ tools.py       # 任务工具
│  │  │  ├─ agents.py      # Agent 组装
│  │  │  └─ rag.py         # 文档检索与问答
│  │  ├─ routers/
│  │  │  ├─ ai.py          # AI 接口
│  │  │  └─ tasks.py       # 任务接口
│  │  └─ main.py           # FastAPI 应用入口
│  ├─ docs/                 # RAG 示例文档
│  ├─ tests/                # pytest 测试
│  └─ pytest.ini
└─ docs/                    # 学习计划与笔记
```

## 安装与配置

进入后端目录并创建虚拟环境：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装主要依赖：

```powershell
pip install "fastapi[standard]" sqlalchemy python-multipart python-dotenv langchain langchain-openai langchain-huggingface langchain-text-splitters sentence-transformers pytest
```

创建 `backend/.env`：

```env
GLM_API_KEY=你的API密钥
```

不要将真实 API Key 提交到版本控制。

## 启动服务

在 `backend` 目录运行：

```powershell
fastapi dev app/main.py
```

启动后可访问：

- 服务地址：`http://127.0.0.1:8000`
- Swagger 文档：`http://127.0.0.1:8000/docs`

## API

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/` | 服务存活检查 |
| GET | `/tasks` | 查询任务列表 |
| POST | `/tasks` | 创建任务 |
| GET | `/tasks/{task_id}` | 查询单个任务 |
| PUT | `/tasks/{task_id}` | 完整更新任务 |
| PATCH | `/tasks/{task_id}` | 部分更新任务 |
| DELETE | `/tasks/{task_id}` | 删除任务 |
| POST | `/upload` | 上传文件 |
| POST | `/ai/chat` | 普通 AI 聊天 |
| POST | `/ai/tasks-assistant` | AI 查询或创建任务 |
| POST | `/ai/rag` | 基于文档问答 |

### 普通聊天

请求：

```json
{
  "message": "什么是 LangChain？"
}
```

### 任务助手

请求：

```json
{
  "message": "查询前 3 条未完成任务"
}
```

也可以要求 Agent 创建任务：

```json
{
  "message": "帮我创建任务：复习 LangChain 测试"
}
```

### RAG 文档问答

请求：

```json
{
  "question": "AgentChat 项目的内部代号是什么？"
}
```

当前 RAG 使用固定文档 `backend/docs/agentchat-guide.md`。`/upload` 负责保存文件，但上传文件尚未自动加入 RAG 索引。

## 运行测试

在 `backend` 目录运行全部测试：

```powershell
pytest tests -v -s
```

只运行 AI 测试：

```powershell
pytest tests/test_ai.py -v -s
```

测试覆盖真实模型调用、请求参数校验，以及使用 `monkeypatch` 模拟的模型、Agent 和 RAG 异常。

RAG 使用 Hugging Face Embedding 模型 `BAAI/bge-small-zh-v1.5`。首次运行需要下载模型；当前测试配置会优先使用本地缓存。

## 技术栈

- FastAPI
- SQLAlchemy 与 SQLite
- LangChain
- OpenAI 兼容模型接口
- Hugging Face Embeddings
- pytest

## 当前限制

- RAG 当前只索引一个固定 Markdown 文档
- 上传文件与 RAG 索引尚未打通
- 向量库使用内存存储，应用重启后会重新构建
- 尚未实现多轮长期记忆和流式输出
