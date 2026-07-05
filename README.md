# AgentChat

AgentChat 是一个前后端分离的 AI 对话与知识库应用。后端基于 FastAPI、SQLAlchemy、LangChain 和 Milvus，前端基于 Next.js、React、Ant Design X 与 Tailwind CSS。

项目目前提供流式 AI 对话、会话历史、文档上传与向量化、RAG 知识库问答、任务助手、JWT 登录，以及管理员系统配置页面。

## 功能概览

- AI 对话：SSE 流式输出，保存会话和消息，生成回答时读取最近 10 条历史消息
- 知识库问答：检索 Milvus 中的相关文档分片，并返回回答与来源
- 文档管理：上传、解析、索引、进度展示、下载和删除 PDF、DOCX、Markdown、TXT
- 任务管理：任务 CRUD，以及可查询待办、创建任务的 LangChain Agent
- 用户认证：JWT 登录、当前用户查询、管理员权限校验
- 系统配置：管理员维护 AI、邮件、通知和向量库配置，敏感值加密存储并脱敏展示
- 邮件通知：文档索引成功或失败后发送处理结果通知
- 响应式前端：桌面侧栏与移动端底部导航，支持普通对话和 RAG 模式切换

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Next.js 16、React 19、TypeScript、Ant Design 6、Ant Design X、Tailwind CSS 4、Axios |
| 后端 | Python 3.11–3.13、FastAPI、SQLAlchemy 2、Pydantic |
| AI | LangChain、OpenAI 兼容的 Chat Completions / Embeddings API |
| 数据 | PostgreSQL 或 SQLite、Milvus |
| 认证与安全 | JWT、bcrypt、Fernet 加密 |
| 工程化 | uv、pytest、Ruff、npm / pnpm、ESLint |

## 项目结构

```text
AgentChat/
├─ backend/
│  ├─ app/
│  │  ├─ ai/                 # 模型、Prompt、Chain、Agent、RAG 与文档解析
│  │  ├─ routers/            # AI、任务、认证和系统配置路由
│  │  ├─ services/           # 认证、配置、加密和邮件服务
│  │  ├─ crud.py             # 数据访问操作
│  │  ├─ database.py         # SQLAlchemy 引擎与会话
│  │  ├─ models.py           # ORM 模型
│  │  ├─ schemas.py          # API 数据模型
│  │  └─ main.py             # FastAPI 应用入口与文档接口
│  ├─ docs/                  # 启动时可加入 RAG 的内置示例文档
│  ├─ tests/                 # pytest 测试
│  ├─ .env.example           # 后端环境变量示例
│  └─ pyproject.toml         # Python 依赖与工具配置
├─ frontend/
│  ├─ src/app/               # chat、knowledge、login、settings 页面
│  ├─ src/components/        # 全局布局等组件
│  ├─ src/lib/               # HTTP 客户端与认证工具
│  └─ package.json
└─ docs/                     # 学习计划与代码笔记
```

## 本地运行

### 1. 环境要求

- Python 3.11–3.13；仓库的 `.python-version` 当前指定 Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 或更高版本
- 可访问的 OpenAI 兼容模型服务
- Milvus 服务，默认地址为 `http://localhost:19530`
- PostgreSQL（可选；未配置时使用 SQLite）

### 2. 配置并启动后端

```powershell
cd backend
Copy-Item .env.example .env
uv sync --extra ai
```

编辑 `backend/.env`，最小可用配置如下：

```env
# OpenAI 兼容的模型服务
LLM_API_KEY=your-api-key
AI_BASE_URL=https://your-provider.example/v1
AI_MODEL=your-chat-model
EMBEDDING_MODEL=your-embedding-model
AGENTCHAT_EMBEDDING_DIMENSIONS=1024

# Milvus
AGENTCHAT_MILVUS_URI=http://localhost:19530
AGENTCHAT_MILVUS_COLLECTION=agentchat_documents

# 请在正式或需要持久登录的环境中固定这两个密钥
JWT_SECRET_KEY=replace-with-a-long-random-secret
ENCRYPTION_KEY=replace-with-a-fernet-key
```

`ENCRYPTION_KEY` 必须是合法的 Fernet 密钥，可以在依赖安装后生成：

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

启动 FastAPI：

```powershell
uv run fastapi dev app/main.py
```

后端默认地址：

- API：<http://127.0.0.1:8000>
- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>

首次启动且用户表为空时，后端会创建管理员。默认账号为 `admin` / `admin123`。建议在第一次启动前通过以下变量改掉默认值：

```env
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=replace-with-a-strong-password
DEFAULT_ADMIN_EMAIL=admin@example.com
```

### 3. 配置并启动前端

```powershell
cd frontend
npm install
```

创建 `frontend/.env.local`：

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

当前代码中，登录页读取 `NEXT_PUBLIC_API_BASE_URL`，其他页面读取 `NEXT_PUBLIC_API_URL`，因此二者应配置为同一个后端地址。

启动开发服务器：

```powershell
npm run dev
```

浏览器访问 <http://localhost:3000>。根路径会自动跳转到 `/chat`。

### 4. 生产构建

```powershell
cd frontend
npm run build
npm run start
```

后端生产部署时应使用固定的 `JWT_SECRET_KEY` 和 `ENCRYPTION_KEY`，配置 PostgreSQL，并用数据库迁移工具替代当前的启动时自动建表。

## 环境变量

### 后端

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./test.db` | SQLAlchemy 数据库地址 |
| `LLM_API_KEY` | 空 | OpenAI 兼容 API 密钥 |
| `AI_BASE_URL` | `https://ai.hybgzs.com/v1` | 模型 API 基础地址 |
| `AI_MODEL` | `moonshotai/kimi-k2.6` | 对话模型名称 |
| `EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-8B` | Embedding 模型名称 |
| `AGENTCHAT_EMBEDDING_DIMENSIONS` | `1024` | Embedding 向量维度，必须与模型及 Milvus 集合一致 |
| `AGENTCHAT_MILVUS_URI` | `http://localhost:19530` | Milvus 服务地址；也支持以 `.db` 结尾的 Milvus Lite 地址 |
| `AGENTCHAT_MILVUS_COLLECTION` | `agentchat_documents` | Milvus 集合名 |
| `AGENTCHAT_MILVUS_TOKEN` | 空 | Milvus 鉴权令牌 |
| `AGENTCHAT_MILVUS_DB` | 空 | Milvus 数据库名 |
| `AGENTCHAT_VECTOR_TIMEOUT_SECONDS` | `60` | 向量操作超时秒数 |
| `JWT_SECRET_KEY` | 启动时随机生成 | JWT 签名密钥；随机值会导致重启后旧令牌失效 |
| `JWT_ALGORITHM` | `HS256` | JWT 签名算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `43200` | 访问令牌有效期，默认 30 天 |
| `ENCRYPTION_KEY` | 启动时随机生成 | 系统敏感配置加密密钥；随机值会导致重启后旧密文无法解密 |
| `DEFAULT_ADMIN_USERNAME` | `admin` | 首次初始化的管理员用户名 |
| `DEFAULT_ADMIN_PASSWORD` | `admin123` | 首次初始化的管理员密码 |
| `DEFAULT_ADMIN_EMAIL` | `admin@agentchat.local` | 首次初始化的管理员邮箱 |

邮件通知还支持以下变量：

```env
SMTP_ENABLED=false
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=sender@example.com
SMTP_PASSWORD=mail-authorization-code
SMTP_FROM_EMAIL=sender@example.com
SMTP_FROM_NAME=AgentChat通知系统
```

通知接收地址可由管理员页面中的 `document_notification_email` 配置。QQ 邮箱应填写授权码，而不是登录密码。

### 前端

| 变量 | 代码默认值 | 使用位置 |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | 对话、知识库和系统设置 |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | 登录页 |

## 使用说明

### AI 对话

前端 `/chat` 提供两种模式：

- 普通对话：调用 `POST /ai/chat/stream`，通过 SSE 逐段显示回答，并持久化会话和消息
- RAG 问答：调用 `POST /ai/rag`，检索知识库并展示来源

普通对话会读取会话最近 10 条消息和 `chat_sessions.summary` 作为上下文。当前会持久化完整历史，但尚未自动生成长期摘要。

### 文档知识库

前端 `/knowledge` 支持上传 `.pdf`、`.docx`、`.md` 和 `.txt`。后端处理流程为：

1. 保存原始文件并创建 `uploaded_documents` 记录
2. 在 FastAPI 后台任务中解析和清洗文本
3. 以 600 字符、100 字符重叠切分文档
4. 生成 Embedding 并写入 Milvus
5. 通过 SSE 接口推送 `parsing`、`chunking`、`indexing` 等进度
6. 根据配置发送成功或失败邮件

PDF 使用 `pypdf` 提取文本，不包含 OCR；扫描件若没有可提取文本会处理失败。TXT 和 Markdown 支持 UTF-8、GB18030 编码，DOCX 由 `python-docx` 解析。

删除文档需要登录。对于已经索引的文档，后端会先删除 Milvus 分片，再删除本地文件和数据库记录；处理中的文档不能删除。

### 系统设置

管理员登录后可以访问 `/settings`。敏感配置（例如 API Key、SMTP 密码）使用 Fernet 加密保存，接口返回时会脱敏。

当前实现中：

- 邮件与通知配置会在发送邮件时从数据库读取
- 聊天、任务助手和 RAG 生成模型会在每次请求时优先读取数据库配置，未配置时回退到 `backend/.env`
- 后台保存 LLM 配置后，下一次 AI 请求立即生效；Embedding 和 Milvus 客户端仍在进程启动时初始化，修改向量配置后需要重启后端

## API 概览

| 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- |
| `GET` | `/` | 存活检查 | 公开 |
| `POST` | `/auth/login` | 登录并获取 JWT | 公开 |
| `GET` | `/auth/me` | 查询当前用户 | 可选登录 |
| `POST` | `/auth/logout` | 登出提示；令牌由客户端清除 | 登录 |
| `GET/POST` | `/tasks` | 查询或创建任务 | 公开 |
| `GET/PUT/PATCH/DELETE` | `/tasks/{task_id}` | 查询、更新或删除任务 | 公开 |
| `GET/POST` | `/ai/sessions` | 查询或创建聊天会话 | 公开 |
| `DELETE` | `/ai/sessions/{session_id}` | 软删除会话（保留消息用于审计） | 公开 |
| `GET` | `/ai/sessions/{session_id}/messages` | 查询会话消息 | 公开 |
| `POST` | `/ai/chat` | 非流式普通对话 | 公开 |
| `POST` | `/ai/chat/stream` | SSE 流式普通对话 | 公开 |
| `POST` | `/ai/tasks-assistant` | AI 任务助手 | 公开 |
| `POST` | `/ai/rag` | RAG 文档问答 | 公开 |
| `POST` | `/upload` | 上传并后台索引文档 | 公开 |
| `GET` | `/documents` | 查询文档记录 | 公开 |
| `GET` | `/documents/{id}/progress` | SSE 文档处理进度 | 公开 |
| `GET` | `/documents/{id}/download` | 下载原始文档 | 公开 |
| `DELETE` | `/documents/{id}` | 删除文档、文件和向量分片 | 登录 |
| `GET/PUT/DELETE` | `/settings/{key}` | 查询、更新或删除配置 | 管理员 |
| `GET` | `/settings` | 查询配置列表 | 管理员 |
| `POST` | `/settings/batch` | 批量保存配置 | 管理员 |

需要认证的接口使用 Bearer Token：

```http
Authorization: Bearer <access_token>
```

完整请求和响应结构以启动后的 Swagger UI 为准。

## 测试与检查

后端：

```powershell
cd backend
uv run pytest tests -v
uv run ruff check app tests
```

`tests/test_ai.py` 中包含真实模型和 RAG 集成请求，运行完整测试集前需准备有效的模型 API 与 Milvus；其余测试大量使用 monkeypatch 隔离外部服务。

前端：

```powershell
cd frontend
npm run lint
npm run build
```

## 当前限制

- 扫描版 PDF 暂不支持 OCR
- 对话长期摘要字段已经预留，但不会自动更新
- AI 与 Milvus 的数据库配置尚未动态接入已初始化的运行时实例
- 除系统设置和文档删除外，多数业务 API 当前仍是公开接口，也没有按用户隔离会话、任务和文档
- 文档后台处理使用 FastAPI 进程内任务，不适合直接作为高可靠任务队列
- 开发阶段由 SQLAlchemy 自动建表，尚未接入 Alembic 数据库迁移

## 数据与安全提示

- 不要提交 `backend/.env`、`frontend/.env.local`、API Key、数据库密码或邮件授权码
- `backend/uploads/`、SQLite 数据库和本地向量文件均为运行时数据，已在 `.gitignore` 中排除
- 生产环境应限制 CORS 来源、启用 HTTPS、使用强密钥，并为当前公开业务接口补充认证和用户级数据隔离
