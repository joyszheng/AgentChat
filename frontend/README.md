# AgentChat 前端工程

这是一个基于 [Next.js](https://nextjs.org) 构建的 AgentChat 前端项目。

该项目负责为 AgentChat 提供现代化的 RAG 知识库问答用户界面，主要集成了：
- **Next.js (App Router)**：全栈应用框架与路由体系。
- **Ant Design & Ant Design X**：提供高品质的通用组件与 AI 对话场景（气泡、发送器等）专用交互组件。
- **Tailwind CSS**：用于快速、高度自定义的页面布局与样式。
- **Axios & AHooks**：提供高效的 HTTP 数据请求拦截和 Hooks 封装。

## 开始使用

### 环境要求
- [Node.js](https://nodejs.org/) 18.17 或更高版本。
- 建议使用 [pnpm](https://pnpm.io/) 作为包管理器。

### 安装依赖

进入 `frontend` 目录并安装依赖包：

```bash
cd frontend
pnpm install
```

### 启动开发服务器

确保 FastAPI 后端服务已启动（默认监听 `http://127.0.0.1:8000`）。
然后运行以下命令启动前端开发服务器：

```bash
pnpm dev
```

打开浏览器访问 [http://localhost:3000](http://localhost:3000) 即可查看页面。

## 目录结构

- `src/app/`：Next.js App Router 的主要路由目录，包含全局布局。
  - `chat/`：基于 Ant Design X 构建的流式对话及 RAG 问答界面。
  - `knowledge/`：知识库管理界面，提供文档上传及状态展示。
- `src/components/`：通用业务组件（如 `AppLayout` 全局侧边栏等）。
- `src/lib/http/`：网络请求模块，包含封装好的 axios 实例。

## 配置与部署

API 的请求根路径默认指向 `http://127.0.0.1:8000`。
若需在生产环境中修改，请在根目录创建 `.env.local` 文件，配置以下变量：

```env
NEXT_PUBLIC_API_URL=https://your-production-api.com
```

如果要进行构建和生产环境部署：

```bash
pnpm build
pnpm start
```

欲了解更多信息，请参阅 [Next.js 文档](https://nextjs.org/docs)。
