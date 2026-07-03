# AgentChat 前端技术栈选型说明

## 1. 选型目标

AgentChat 前端需要支持聊天会话、AI 流式响应、文件上传、用户配置及后续管理页面。本次选型重点考虑：

- 良好的 TypeScript 类型安全与工程化能力；
- 适配 AI 聊天、流式内容和复杂交互；
- 支持服务端渲染，并兼顾首屏体验与后续扩展；
- 使用成熟组件库提高交付效率；
- 统一包管理、代码质量和自动化测试方案。

## 2. 最终技术栈

| 类别 | 技术选型 | 主要用途 |
| --- | --- | --- |
| 前端框架 | Next.js（App Router） | 路由、页面渲染、服务端组件和前端工程构建 |
| 开发语言 | TypeScript（Strict Mode） | 类型检查、接口约束和重构安全性 |
| 构建工具 | Next.js 内置 Turbopack | 本地开发和生产构建 |
| 包管理器 | pnpm | 依赖安装、锁定和脚本执行 |
| 基础组件库 | antd | 表单、弹窗、菜单、反馈及通用业务组件 |
| AI 聊天组件 | Ant Design X | 消息气泡、会话列表、发送器及 AI 交互组件 |
| 样式方案 | Tailwind CSS | 页面布局、间距、响应式和局部样式 |
| 普通 HTTP 请求 | Axios | 登录、用户、会话列表、历史消息及普通 CRUD 请求 |
| 流式请求 | Fetch API / `@ant-design/x-sdk` | SSE、ReadableStream 和 AI 流式响应 |
| 代码质量 | ESLint + Prettier | 静态检查与代码格式统一 |
| 单元和组件测试 | Vitest + Testing Library | 工具函数、状态逻辑和组件行为测试 |
| 端到端测试 | Playwright | 登录、创建会话、发送消息等完整用户流程测试 |

## 3. 核心选型说明

### 3.1 Next.js 与 Vite

主应用使用 Next.js，不再额外引入 Vite。Next.js 已提供路由、服务端渲染、开发服务器和生产构建能力，并默认使用 Turbopack。叠加 Vite 会产生两套构建配置和环境变量规则，增加维护成本。

Vitest 虽然基于 Vite 的测试能力，但它只作为测试运行器使用，不代表项目使用 Vite 构建。

### 3.2 App Router

项目采用 App Router，并使用 `src/app` 组织路由。默认优先使用 Server Component；只有需要浏览器状态、事件处理、Ant Design 交互组件或客户端请求的模块才声明 `"use client"`。

antd 与 Ant Design X 在 App Router 中通过 `@ant-design/nextjs-registry` 注入首屏样式，避免服务端渲染时出现样式闪烁。

### 3.3 Axios 与 Fetch 的边界

Axios 统一处理非流式 API 请求，集中配置：

- API Base URL；
- 登录凭证和请求头；
- 超时及错误映射；
- 401 等通用响应处理。

AI 对话的流式返回使用原生 Fetch API 或 `@ant-design/x-sdk`。浏览器端 Axios 通常不适合作为 ReadableStream 消费层，不应让普通 Axios 实例承担流式聊天职责。

### 3.4 antd、Ant Design X 与 Tailwind CSS

三套方案按职责使用：

- antd 负责标准业务组件；
- Ant Design X 负责 AI 聊天场景组件；
- Tailwind CSS 负责页面布局、间距、响应式和少量局部样式；
- antd Design Token 负责组件主题、颜色、圆角和字号。

禁止大量使用 Tailwind `!important` 或深层选择器覆盖 antd 内部结构。需要调整组件视觉时，应优先使用 Design Token、组件属性或外层封装。

### 3.5 TypeScript

TypeScript 开启严格模式。接口请求、聊天消息、会话、用户和附件等核心数据必须定义明确类型，避免在业务代码中扩散 `any`。

建议后续根据后端 OpenAPI 文档自动生成请求和响应类型，减少前后端字段不一致问题。

## 4. 推荐目录结构

```text
fontend/
├─ doc/                    # 前端设计及工程文档
├─ public/                 # 静态资源
├─ src/
│  ├─ app/                 # Next.js App Router 页面与布局
│  ├─ components/          # 跨业务通用组件
│  ├─ features/
│  │  ├─ chat/             # 聊天页面、消息流和会话状态
│  │  ├─ auth/             # 登录与身份认证
│  │  └─ settings/         # 用户及模型配置
│  ├─ lib/
│  │  ├─ http/             # Axios 实例、拦截器和错误处理
│  │  └─ stream/           # Fetch 流式请求解析
│  ├─ services/            # 后端 API 服务封装
│  ├─ types/               # 跨模块 TypeScript 类型
│  └─ styles/              # 全局样式和主题配置
├─ tests/                  # Vitest 测试
└─ e2e/                    # Playwright 测试
```

## 5. 工程规范

- 统一使用 pnpm，提交 `pnpm-lock.yaml`，不混用 npm 或 yarn；
- 使用 `@/*` 作为 `src/*` 路径别名；
- 依赖版本由 `package.json` 和锁文件共同管理，不在业务代码中依赖未公开 API；
- API 调用必须通过 `services` 或 `lib` 封装，页面组件不直接散落请求配置；
- 核心工具函数和状态逻辑使用 Vitest 测试；
- 登录、创建会话、发送消息和流式响应等关键路径使用 Playwright 测试；
- 环境变量按 Next.js 规则管理，只有允许暴露给浏览器的变量使用 `NEXT_PUBLIC_` 前缀。

## 6. 暂不引入的技术

- **Vite**：与 Next.js 主构建体系重复；
- **大型全局状态库**：初期优先使用组件状态、Context 和 Ant Design X 提供的数据流能力，出现明确跨页面复杂状态后再评估 Zustand；
- **多套 UI 组件库**：避免额外引入功能重叠的组件库，保持交互与视觉一致。

## 7. 官方资料

- [Next.js 安装与 App Router](https://nextjs.org/docs/app/getting-started/installation)
- [Next.js 数据请求](https://nextjs.org/docs/app/getting-started/fetching-data)
- [Ant Design 在 Next.js 中使用](https://ant.design/docs/react/use-with-next/)
- [Ant Design X 在 Next.js 中使用](https://x.ant.design/docs/react/use-with-next-cn/)
- [Tailwind CSS 的 Next.js 指南](https://tailwindcss.com/docs/installation/framework-guides/nextjs)
- [Vitest](https://vitest.dev/)
- [Playwright](https://playwright.dev/)
