# AgentChat

AgentChat 是一个用于学习 FastAPI、SQLAlchemy 与 LangChain 的 AI 任务助手后端。

## 已实现功能

- 任务的创建、查询、更新和删除
- 普通 AI 聊天
- 多轮聊天会话与历史消息持久化
- AI 查询未完成任务
- AI 创建任务
- 基于固定文档和上传文档的 RAG 问答
- 文件上传、文本解析、清洗与 RAG 入库
- pytest 接口与异常测试
- 文档处理完成邮件通知

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
│  │  │  ├─ document_processing.py # 上传文档解析与清洗
│  │  │  └─ rag.py         # 文档检索、切分与索引
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

项目使用 `uv` 统一管理 Python、虚拟环境、依赖和锁文件。Windows 可使用官方脚本安装：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

进入后端目录并同步完整开发环境：

```powershell
cd backend
uv sync --extra ai
```

`uv` 会根据 `.python-version` 准备 Python 3.11、创建 `.venv`，并在首次同步时生成 `uv.lock`。普通 Web 与数据库依赖位于基础依赖组，LangChain、线上模型客户端、文档解析等依赖位于 `ai` 可选组，pytest、ruff 等开发工具位于 `dev` 组。当前应用启动时会注册 AI 路由，因此运行完整服务必须带上 `--extra ai`。

创建 `backend/.env`：

```env
GLM_API_KEY=你的API密钥
DATABASE_URL=postgresql+psycopg://postgres:你的PostgreSQL密码@localhost:5432/postgres
AGENTCHAT_MILVUS_URI=http://localhost:19530
AGENTCHAT_MILVUS_COLLECTION=agentchat_documents
AGENTCHAT_EMBEDDING_DIMENSIONS=1024
# 如果 Milvus 开启鉴权，再配置：
# AGENTCHAT_MILVUS_TOKEN=root:Milvus
# AGENTCHAT_MILVUS_DB=default

# 邮件通知配置（可选）
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的QQ邮箱地址
SMTP_PASSWORD=你的QQ邮箱授权码
SMTP_FROM_EMAIL=你的QQ邮箱地址
SMTP_FROM_NAME=AgentChat通知系统
SMTP_ENABLED=true
```

不要将真实 API Key 或数据库密码提交到版本控制。未配置 `DATABASE_URL` 时，后端会回退使用本地 SQLite 文件 `backend/test.db`。

### 邮件通知配置（可选）

项目支持在文档处理完成后发送邮件通知。当前通知接收地址配置在 `backend/app/main.py` 的 `DOCUMENT_NOTIFICATION_EMAIL` 常量中。

**QQ 邮箱配置步骤：**

1. 登录 QQ 邮箱网页版，进入「设置」→「账户」
2. 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务」
3. 开启「IMAP/SMTP服务」或「POP3/SMTP服务」
4. 点击「生成授权码」，按提示完成验证
5. 将生成的授权码填入 `.env` 的 `SMTP_PASSWORD` 字段

**注意**：`SMTP_PASSWORD` 填写的是授权码，不是 QQ 密码。

如果不需要邮件通知，可以将 `SMTP_ENABLED` 设为 `false`，或不配置 `SMTP_USER` 和 `SMTP_PASSWORD`。

邮件通知内容包括：
- 文件名和文件大小
- 上传时间
- 处理状态（成功/失败）
- 文档数量和文本分片数
- 警告信息或错误信息

## 启动服务

在 `backend` 目录运行：

```powershell
uv run fastapi dev app/main.py
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
| GET | `/documents` | 查询上传文档记录 |
| POST | `/ai/sessions` | 创建聊天会话 |
| GET | `/ai/sessions` | 查询聊天会话列表 |
| GET | `/ai/sessions/{session_id}/messages` | 查询会话消息 |
| POST | `/ai/chat` | 普通 AI 聊天 |
| POST | `/ai/tasks-assistant` | AI 查询或创建任务 |
| POST | `/ai/rag` | 基于文档问答 |

### 普通聊天

请求：

```json
{
  "message": "什么是 LangChain？",
  "session_id": 1
}
```

`session_id` 可选；不传时后端会自动创建新会话，传入时会继续该会话。聊天时会读取当前会话最近 10 条历史消息，并与 `chat_sessions.summary` 一起组成上下文传给模型。

响应：

```json
{
  "answer": "LangChain 是一个用于构建 LLM 应用的开发框架。",
  "session_id": 1,
  "user_message_id": 10,
  "assistant_message_id": 11
}
```

### 多轮会话

创建会话：

```http
POST /ai/sessions
```

```json
{
  "title": "AgentChat 开发讨论",
  "mode": "chat"
}
```

查询会话列表：

```http
GET /ai/sessions?skip=0&limit=20
```

查询会话消息：

```http
GET /ai/sessions/1/messages?skip=0&limit=50
```

会话和消息分别保存到数据库表 `chat_sessions` 与 `chat_messages`。`chat_sessions.summary` 已预留为长期摘要记忆字段；当前版本会持久化完整消息历史，并在回答时使用最近 10 条历史消息，自动摘要压缩将在后续版本实现。

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

当前 RAG 启动时会索引固定文档 `backend/docs/agentchat-guide.md`。上传 `.pdf`、`.docx`、`.md`、`.txt` 文件后，后端会使用 `unstructured` 提取文本，清洗后切分为 chunk，并加入 Milvus 向量索引。

向量库使用 Milvus 服务模式，默认连接 `http://localhost:19530`，集合名为 `agentchat_documents`。可以用 Attu 查看集合、schema 和数据：

- Attu 桌面版连接：`localhost:19530`
- Attu Docker 连接宿主机 Milvus：`host.docker.internal:19530`
- Attu 与 Milvus 在同一 Docker 网络：`milvus:19530`

如果 Milvus 开启鉴权，在 `.env` 中配置 `AGENTCHAT_MILVUS_TOKEN`；如果使用非默认数据库，配置 `AGENTCHAT_MILVUS_DB`。

### 文件上传与入库

`/upload` 会保存原始文件并返回 `202 Accepted`，随后在后台解析文本并自动加入 RAG 索引。当前支持：

- `.pdf`
- `.docx`
- `.md`
- `.txt`

请求使用 `multipart/form-data` 上传文件字段 `file`。

接收成功响应示例：

```json
{
  "document_id": 1,
  "filename": "3f2b...c9.pdf",
  "original_filename": "制度文件.pdf",
  "content_type": "application/pdf",
  "size": 12345,
  "saved_to": "D:\\project\\AgentChat\\backend\\uploads\\3f2b...c9.pdf",
  "indexed": false,
  "status": "processing",
  "document_count": 0,
  "chunk_count": 0,
  "warnings": [],
  "message": "文件上传成功，正在后台解析并加入 RAG 索引"
}
```

客户端可通过 `GET /documents` 查询后台处理结果。状态会从 `processing` 变为 `indexed`；解析或入库失败时变为 `failed`，具体原因记录在 `error_message`。

后台处理进度会输出到 FastAPI 服务终端，日志前缀包括 `[upload:<文档ID>]`、`[document]` 和 `[rag]`，可据此判断当前处于文件解析、文本切块、Embedding 或 Milvus 写入阶段，并查看各阶段耗时。

PDF 当前使用轻量 `pypdf` 解析，只处理可以直接提取文本的 PDF；扫描件 PDF 暂不启用 OCR，若未提取到可用文本，后台记录会标记为 `failed`。DOCX、Markdown 和 TXT 仍由 `unstructured` 处理。

上传文件会写入数据库表 `uploaded_documents`，记录原文件名、服务端文件名、保存路径、文件大小、解析状态、chunk 数、文件 hash、错误信息和创建/更新时间。当前开发阶段启动时会调用 SQLAlchemy 自动建表；生产环境建议改用 Alembic 等迁移工具。文档 chunk 和向量写入 Milvus，不存入 PostgreSQL。

### 上传文档记录

查询上传文档记录：

```http
GET /documents?skip=0&limit=20
```

响应字段包含：

```json
[
  {
    "id": 1,
    "original_filename": "制度文件.pdf",
    "stored_filename": "3f2b...c9.pdf",
    "content_type": "application/pdf",
    "file_ext": ".pdf",
    "size_bytes": 12345,
    "saved_to": "D:\\project\\AgentChat\\backend\\uploads\\3f2b...c9.pdf",
    "status": "indexed",
    "document_count": 12,
    "chunk_count": 38,
    "file_sha256": "...",
    "warnings": [],
    "error_message": null,
    "created_at": "2026-06-30T10:00:00",
    "updated_at": "2026-06-30T10:00:03"
  }
]
```

## 运行测试

在 `backend` 目录运行全部测试：

```powershell
uv run pytest tests -v -s
```

只运行 AI 测试：

```powershell
uv run pytest tests/test_ai.py -v -s
```

## 依赖维护

在 `backend` 目录使用以下命令维护依赖，不要直接执行 `pip install` 修改项目环境：

```powershell
# 添加运行依赖
uv add pydantic-settings

# 添加 PostgreSQL 驱动
uv add "psycopg[binary]"

# 添加 AI 可选依赖
uv add --optional ai langchain-community

# 添加 Milvus 向量库依赖
uv add pymilvus langchain-milvus

# 添加文档解析依赖（不启用 OCR）
uv add --optional ai unstructured pdfminer-six python-docx markdown

# 添加开发依赖
uv add --dev pytest-cov

# 只升级一个包，减少批量升级风险
uv lock --upgrade-package langchain

# 查看完整依赖树
uv tree
```

修改依赖后应同时提交 `pyproject.toml` 和 `uv.lock`。CI 或部署环境建议使用 `uv sync --locked --extra ai --no-dev`，确保锁文件与项目声明一致。

测试覆盖真实模型调用、请求参数校验，以及使用 `monkeypatch` 模拟的模型、Agent 和 RAG 异常。

RAG 使用 OpenAI 兼容 embedding 接口，地址和密钥复用 `backend/app/ai/models.py` 中的 `AI_BASE_URL` 与 `GLM_API_KEY`，embedding 模型为 `baai/bge-m3`。运行 RAG 前需要确保 `.env` 中已配置可用的 `GLM_API_KEY`。

## 技术栈

- FastAPI
- SQLAlchemy、PostgreSQL 与 SQLite 回退
- LangChain
- Milvus
- OpenAI 兼容模型接口
- OpenAI 兼容 Embeddings
- unstructured 文档解析
- pytest

## 当前限制

- 需要先启动 Milvus 服务，默认地址为 `http://localhost:19530`
- PDF 仅支持可提取文本的文档，扫描件 OCR 暂未启用
- 多轮聊天已持久化消息历史，但长期摘要自动更新尚未实现
- 尚未实现流式输出
