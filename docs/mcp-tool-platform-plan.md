# AgentChat 通用 MCP 工具平台规划

## 1. 背景与目标

AgentChat 当前只有任务助手使用 LangChain Agent，普通聊天仍是 `Prompt | LLM` Chain。项目需要增加一个与具体工具类型无关的 MCP 接入层，使管理员可以注册不同的 MCP Server，并将允许的工具提供给大模型。

本规划的目标不是只接入搜索，而是建设以下通用能力：

- 注册和管理多个 MCP Server
- 自动发现 MCP Tools
- 通过白名单决定哪些工具可以暴露给模型
- 处理服务器鉴权、健康状态、超时和错误
- 根据用户权限动态选择工具
- 保存工具调用审计信息
- 为后续流式工具状态、用户审批、MCP Resources 和 Prompts 预留扩展点

## 2. 当前项目基础

### 已具备

- FastAPI lifespan，可承载 MCP Client 生命周期
- LangChain `create_agent`，任务助手已有工具调用示例
- LLM 按请求从数据库动态加载
- JWT 用户和管理员权限
- Fernet 敏感配置加密
- 聊天会话、消息及 `message_metadata`
- SSE 普通聊天输出

### 尚缺少

- `langchain-mcp-adapters` 依赖
- MCP Server 和工具策略数据模型
- MCP Client Registry
- MCP 管理 API
- 通用 Assistant Agent
- 工具调用事件和前端状态展示
- 写操作审批与完整审计

## 3. 总体架构

```text
用户请求
  |
  v
Assistant Agent ---- 当前请求对应的 LLM
  |
  v
MCP Registry
  |-- Server A / Tool A
  |-- Server A / Tool B
  |-- Server B / Tool A
  `-- 后续本地 LangChain Tools
  |
  v
远程 Streamable HTTP MCP Servers
```

MCP 接入层与 Agent 编排层保持分离。MCP Registry 负责连接、发现、过滤和调用；Agent 只获取当前用户被允许使用的 LangChain Tool。

## 4. 首期范围

首期实现一个安全、可测试的最小闭环：

1. 仅支持远程 Streamable HTTP MCP Server
2. 管理员创建、修改、删除、测试和重载 MCP Server
3. 认证 Headers 加密存储，接口只返回 Header 名称
4. 自动发现工具并保存工具名称
5. 工具采用 `server__tool` 命名空间，避免重名
6. 只有白名单中的工具可以被调用
7. Server 默认只向管理员开放
8. 提供管理员手动工具调用接口
9. 提供独立的、需要登录的非流式 MCP Assistant 接口
10. 不替换现有普通聊天、RAG 和任务助手

### 首期明确不做

- stdio MCP Server
- 普通聊天流式 Agent 化
- 写操作人工审批
- 用户级 OAuth
- MCP Resources 和 Prompts
- 无重启的连接配置热切换优化
- 前端 MCP 管理页面

## 5. 数据设计

### `mcp_servers`

| 字段 | 说明 |
| --- | --- |
| `name` | 全局唯一服务器名称，也是工具命名空间 |
| `description` | 管理员备注 |
| `transport` | 首期固定为 `streamable_http` |
| `url` | MCP Streamable HTTP 地址 |
| `headers_encrypted` | 加密后的认证 Header JSON |
| `enabled` | 是否参与运行时加载 |
| `require_admin` | 是否只向管理员提供工具 |
| `allowed_tools` | 工具白名单，支持 `*` |
| `discovered_tools` | 最近一次成功发现的工具名称 |
| `call_timeout_seconds` | 单次工具调用超时 |
| `max_result_chars` | 返回给模型的字符串最大长度 |
| `last_health_status` | `unknown / healthy / unhealthy / disabled` |
| `last_error` | 最近连接或发现错误 |
| `last_checked_at` | 最近检查时间 |

### 后续表

后续增加 `mcp_tool_policies` 和 `mcp_tool_call_logs`，支持每个工具的风险等级、审批规则及独立审计。首期先把调用摘要写入聊天消息 `message_metadata`，管理接口调用只写应用日志。

## 6. 安全边界

- 仅管理员可以管理、测试和手动调用 MCP 工具
- Assistant 接口必须登录；Server 默认 `require_admin=true`
- 工具必须在本地白名单中才能暴露
- 不信任远端工具名称、描述和安全注解
- 不在 API 响应、日志或消息元数据中保存认证 Header 明文
- 工具参数限制为 MCP Schema，并设置超时和字符串结果长度上限
- stdio 在首期禁用，避免任意本地命令执行风险
- MCP 失败不得阻止 FastAPI 启动，运行时应降级并提供健康状态

## 7. API 规划

```http
GET    /mcp/servers
POST   /mcp/servers
GET    /mcp/servers/{id}
PUT    /mcp/servers/{id}
DELETE /mcp/servers/{id}
POST   /mcp/servers/{id}/test
POST   /mcp/reload
GET    /mcp/tools
POST   /mcp/tools/{qualified_name}/invoke

POST   /ai/mcp-assistant
```

## 8. 分阶段计划

### 阶段一：通用 MCP 基础层

- [x] 添加 MCP 依赖
- [x] 增加 `mcp_servers` 数据模型和请求响应模型
- [x] 实现 MCP Registry
- [x] 实现连接测试、工具发现、白名单和命名空间
- [x] 实现管理 API
- [x] 增加单元测试

### 阶段二：独立 MCP Assistant

- [ ] 验证当前实际模型的 Tool Calling
- [x] 新增独立非流式 MCP Agent 接口
- [x] 按用户角色过滤工具
- [x] 保存工具名称到消息元数据
- [ ] 增加模型不支持工具调用时的错误提示

### 阶段三：流式交互

- [ ] 定义 `tool_start / tool_result / approval_required` SSE 事件
- [ ] 普通聊天可选升级为 Agent
- [ ] 前端显示工具状态和来源
- [ ] 历史消息恢复工具元数据

### 阶段四：生产安全

- [ ] 独立工具策略表
- [ ] 只读、写入、危险工具风险等级
- [ ] 写操作审批、暂停和恢复
- [ ] 调用审计、参数脱敏、限流和缓存
- [ ] 用户级 OAuth
- [ ] 可控的 stdio 支持

## 9. 当前进度

更新时间：2026-07-04

- [x] 重新核对当前 AI、配置、路由、会话和前端流式实现
- [x] 确定采用“进程级 MCP Registry + 请求级 Agent”架构
- [x] 确定首期只支持远程 HTTP 和白名单工具
- [x] 创建本规划文档
- [x] 阶段一代码实现
- [x] 阶段二非流式接口与权限过滤
- [x] MCP 单元和 API 测试
- [ ] 使用真实远程 MCP Server 做端到端验证
- [ ] 使用当前实际模型验证 Tool Calling
- [ ] 阶段三流式交互

### 2026-07-04 实施记录

已完成：

- 增加 `langchain-mcp-adapters 0.3.x` 和 MCP SDK 锁定依赖
- 增加 `mcp_servers` 表，应用启动时由现有 SQLAlchemy `create_all` 创建
- 增加进程级 `MCPRegistry`，在 FastAPI lifespan 中加载和释放
- 适配 0.3.x 使用的 `streamable_http` transport
- 加密保存远端认证 Headers，API 只返回 Header 名称
- 工具统一转换为最长 64 字符的 `server__tool` 名称
- 支持工具白名单、管理员限定、调用超时和字符串结果裁剪
- 增加 MCP Server CRUD、连接测试、重载、工具列表和管理员调用 API
- 增加需要登录的 `POST /ai/mcp-assistant`
- Assistant 消息元数据记录 `model=mcp-assistant` 和 `tools_used`

验证结果：

- MCP 专项测试：8 项通过（包含 MCP SDK + Streamable HTTP ASGI 端到端测试）
- 排除真实模型测试和当前已知上传鉴权旧断言后：30 项通过
- Ruff 对本次新增和改动文件检查通过
- 应用 OpenAPI 已包含 MCP 管理接口和 `/ai/mcp-assistant`

尚未验证：

- 尚未连接外部部署的真实远程 MCP Server；当前已通过 MCP SDK 的进程内 Streamable HTTP ASGI 端到端验证
- 尚未对当前数据库中实际选择的模型执行 Tool Calling 探针
- 尚未实现 Agent 流式工具事件和前端管理页面

现有测试注意事项：

- 完整旧测试集中有 3 个上传测试仍按“匿名用户可删除文档”断言，当前业务代码已经要求登录，因此会得到 `401`。这与 MCP 改动无关。

## 10. 关键风险

1. 当前实际模型是否完整支持 Tool Calling，需要用无副作用工具单独验证。
2. MCP Server 的工具定义可能变化，必须使用本地白名单和命名空间。
3. 通用工具可能包含写入或删除操作，首期默认管理员可用，后续必须增加审批。
4. MCP 工具通常是异步调用，现有同步 Agent 接口需要新增异步路径。
5. 普通聊天 SSE 目前只处理文本，不能直接承载 Agent 工具事件。

## 11. 当前 API 使用流程

所有 MCP 管理接口都需要管理员 Bearer Token。

### 1. 注册但暂不启用

```http
POST /mcp/servers
```

```json
{
  "name": "example",
  "description": "示例远程 MCP",
  "transport": "streamable_http",
  "url": "https://mcp.example.com/mcp",
  "headers": {
    "Authorization": "Bearer replace-me"
  },
  "enabled": false,
  "require_admin": true,
  "allowed_tools": []
}
```

### 2. 测试连接并发现工具

```http
POST /mcp/servers/{server_id}/test
```

响应会列出源工具名与 AgentChat 生成的 `server__tool` 名称。

### 3. 配置白名单并启用

```http
PUT /mcp/servers/{server_id}
```

```json
{
  "enabled": true,
  "allowed_tools": ["read_data", "search"]
}
```

更新接口会自动刷新运行时 Registry。也可以手动调用：

```http
POST /mcp/reload
```

### 4. 管理员手动验证工具

```http
POST /mcp/tools/example__search/invoke
```

```json
{
  "arguments": {
    "query": "AgentChat"
  }
}
```

### 5. 让大模型自主选择 MCP 工具

```http
POST /ai/mcp-assistant
```

```json
{
  "message": "使用可用工具查询相关信息",
  "session_id": null
}
```

该接口需要登录，根据用户角色过滤工具；当前为非流式接口，不影响原有 `/ai/chat/stream`。
