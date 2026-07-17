# AgentChat 权限与多用户隔离优化方案

## 背景

当前项目已经具备 JWT 登录、任务用户隔离、管理员系统设置、MCP Server 管理等能力，但聊天会话、知识库文档、RAG 检索和部分 AI 接口仍存在公开访问或弱隔离问题。

本方案用于记录后续实现权限收口和多用户数据隔离的优化路线。第一阶段目标不是做复杂组织权限，而是先保证：登录用户只能访问自己的业务数据，管理员配置仍然只允许管理员访问。

## 目标

- 聊天会话、聊天消息、上传文档、文档向量、任务和任务运行记录按用户隔离。
- 未登录用户不能访问聊天、RAG、文档上传、文档下载、文档列表等业务接口。
- 管理员接口继续只允许管理员访问。
- RAG 检索不能串到其他用户上传的文档。
- 删除文档时只能删除当前用户自己的本地文件和向量分片。
- 前端页面和流式请求统一携带认证信息。

## 资源分类

### 用户私有资源

- 聊天会话：`chat_sessions`
- 聊天消息：`chat_messages`
- 上传文档：`uploaded_documents`
- 文档向量：Milvus metadata 中的文档 chunk
- 任务：`tasks`
- 任务运行记录：`task_runs`

### 管理员全局资源

- 系统设置：`system_settings`
- MCP Server 配置：`mcp_servers`
- 模型配置、Embedding 配置、邮件配置

### 可选共享资源

知识库文档后续可以扩展 `visibility` 字段：

- `private`：仅上传者可见
- `shared`：指定用户或团队可见
- `public`：所有登录用户可见

第一阶段建议默认全部私有。内置示例知识可作为系统默认知识单独标记。

## 后端接口收口

以下接口应改为必须登录：

- `POST /ai/sessions`
- `GET /ai/sessions`
- `DELETE /ai/sessions/{session_id}`
- `GET /ai/sessions/{session_id}/messages`
- `POST /ai/chat`
- `POST /ai/chat/stream`
- `POST /ai/assistant`
- `POST /ai/assistant/stream`
- `POST /ai/rag`
- `POST /ai/rag/stream`
- `POST /upload`
- `GET /documents`
- `GET /documents/{document_id}/download`
- `GET /documents/{document_id}/progress`

继续保持公开或特殊处理：

- `GET /`：健康检查
- `POST /auth/login`：登录
- `GET /auth/me`：可继续 optional，也可以改为必须登录
- `/docs`、`/openapi.json`：生产环境建议关闭或加保护

已经具备鉴权的接口继续保留：

- `/tasks/*`：登录用户
- `/settings/*`：管理员
- `/mcp/*`：管理员

## 数据模型调整

新增字段：

- `chat_sessions.user_id -> users.id`
- `uploaded_documents.user_id -> users.id`

可选字段：

- `chat_messages.user_id -> users.id`

`chat_messages` 可以通过 `session_id` 归属到用户；但直接增加 `user_id` 有利于审计和查询。第一阶段可以不加，避免扩大迁移面。

迁移策略：

1. 新字段先允许 `nullable=True`。
2. 迁移脚本将历史数据归属给默认管理员或指定 legacy 用户。
3. 业务代码创建新数据时强制写入 `user_id`。
4. 稳定后再考虑将字段改为 `nullable=False`。

历史数据处理建议：

- 如果用户表只有一个管理员，把旧会话和旧文档归属给该管理员。
- 如果存在多个用户，不自动猜测归属，优先归属给管理员或单独创建 legacy owner。
- 旧向量数据若没有 `user_id` metadata，第一阶段只允许管理员或系统默认知识检索。

## CRUD 隔离规则

所有用户私有资源查询都必须带 `user_id` 条件。

聊天会话：

- `create_chat_session(db, ..., user_id=user.id)`
- `list_chat_sessions(db, user_id=user.id)`
- `get_chat_session(db, session_id, user_id=user.id)`
- `delete_chat_session(db, session_id, user_id=user.id)`
- `list_chat_messages` 先检查 session 归属，再查询消息

文档：

- `create_uploaded_document(db, ..., user_id=user.id)`
- `list_uploaded_documents(db, user_id=user.id)`
- `get_uploaded_document(db, document_id, user_id=user.id)`
- 下载、删除、进度 SSE 都必须先校验文档归属

任务：

- 现有 `tasks.user_id` 和 `task_runs.user_id` 已经具备隔离基础。
- 继续确保所有任务 CRUD 都传入当前用户 ID。

管理员是否可以通过普通接口查看所有用户数据，第一阶段不建议开放。若确实需要，应另做 `/admin/*` 管理接口，避免普通接口混入管理员绕过逻辑。

## RAG 与向量隔离

文档入库时，每个 chunk metadata 必须写入：

```json
{
  "document_id": 123,
  "user_id": 45,
  "original_filename": "example.pdf"
}
```

检索时必须按当前用户过滤：

```text
metadata["user_id"] == 当前用户 ID
```

如果保留内置默认知识，可以将检索条件设计为：

```text
metadata["user_id"] == 当前用户 ID OR metadata["document_type"] == "default"
```

删除文档向量时优先按更严格条件删除：

```text
metadata["document_id"] == 文档 ID AND metadata["user_id"] == 当前用户 ID
```

注意点：

- 不应只依赖文件名或 hash 删除向量，避免误删其他用户相同文件。
- 旧数据没有 `user_id` 时，必须有兼容策略，不能让普通用户检索到 legacy chunk。
- RAG 默认知识和用户上传知识应在 metadata 上明确区分。

## 前端调整

页面保护：

- 未登录访问 `/chat`、`/knowledge`、`/tasks` 时跳转 `/login`。
- 非管理员访问 `/settings`、`/mcp` 时显示无权限或跳转。
- 不再只依赖隐藏导航入口来保护页面，后端必须最终兜底。

请求认证：

- 普通 axios 请求继续携带 `Authorization: Bearer <token>`。
- 聊天、RAG、assistant 的 `fetch` 流式请求继续携带 Authorization。
- 文档进度当前使用 `EventSource`，原生 `EventSource` 不方便加 Authorization，建议改为 `fetch` 读取 SSE 流。

Token 存储：

- 当前 `access_token` 存在 `localStorage`，第一阶段可以暂不改。
- 后续生产化建议迁移到 HttpOnly Cookie，降低 XSS 窃取 token 的风险。

## 测试计划

后端测试：

- 未登录不能创建、读取、删除聊天会话。
- 未登录不能调用聊天、assistant、RAG 接口。
- 未登录不能上传、列出、下载、删除文档。
- A 用户不能看到 B 用户的聊天会话。
- A 用户不能读取 B 用户的聊天消息。
- A 用户不能下载 B 用户的文档。
- A 用户不能删除 B 用户的文档。
- A 用户不能订阅 B 用户文档的进度流。
- A 用户 RAG 检索不到 B 用户上传的文档。
- 删除文档时只删除当前用户的向量 chunk。
- 管理员设置和 MCP 接口仍然只允许管理员访问。
- 历史 nullable 数据不会导致接口 500。

前端验证：

- 未登录打开业务页面跳转登录页。
- 登录后聊天、知识库、上传、下载、进度流可正常工作。
- 非管理员看不到或无法进入设置、MCP 页面。
- 401 响应会清理登录状态并跳转登录页。

## 推荐实施顺序

1. 新增 Alembic 迁移：`chat_sessions.user_id`、`uploaded_documents.user_id`。
2. 更新 ORM model 和 Pydantic response。
3. 更新 CRUD，给会话和文档查询加 `user_id` 过滤。
4. 更新 AI 路由和文档路由，统一接入 `require_auth`。
5. 更新 RAG 入库、检索、删除逻辑，metadata 带 `user_id`。
6. 更新前端文档进度 SSE，避免 `EventSource` 无法带 Authorization。
7. 补充后端隔离测试。
8. 跑 `uv run pytest tests -q`、`npm run lint`、`npm run build`。

## 暂不纳入第一阶段

- 团队、组织、租户体系。
- 文档共享、协作编辑、公开知识库 UI。
- 细粒度 RBAC 权限矩阵。
- token 从 localStorage 迁移到 HttpOnly Cookie。
- 管理员跨用户数据审计后台。

这些能力可以在用户私有隔离稳定后再逐步设计。
