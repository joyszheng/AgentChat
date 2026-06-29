# LangChain 4 天学习计划

目标：基于你已经掌握的 FastAPI、SQLite、SQLAlchemy ORM 和项目结构能力，在 4 天内学会使用 LangChain 构建一个可接入后端项目的 AI 应用。

最终成果：完成一个「AI 任务助手 + 文档问答」小项目，支持普通聊天、调用任务数据库、创建任务、上传文档、基于文档问答，并通过 FastAPI 暴露接口。

---

## 总体路线

```text
第 1 天：LangChain 基础、模型调用、Prompt、Chain
第 2 天：Tools、Agent、让 AI 调用任务系统
第 3 天：RAG、文档加载、Embedding、向量检索
第 4 天：接入 FastAPI、项目结构整理、测试与复盘
```

学习节奏建议：

```text
讲解 30%
动手 60%
复盘 10%
```

不要一开始追求“大而全”的 Agent 系统。先把最小闭环跑通：输入问题 -> 调用模型 -> 得到结果 -> 接入接口。

---

## 第 1 天：LangChain 基础与第一个 Chain

### 学习目标

理解 LangChain 的基本作用，并能完成第一个模型调用和 Prompt Chain。

你需要掌握：

- LangChain 是什么
- Chat Model 是什么
- Message 的基本概念
- `invoke()` 的使用
- `ChatPromptTemplate`
- Chain 的组合方式
- 如何把 LangChain 接入一个简单 FastAPI 接口

### 核心概念

LangChain 可以理解为：

```text
用于组织 LLM 调用流程的 Python 框架
```

FastAPI 和 LangChain 的分工：

```text
FastAPI   负责提供 HTTP API
LangChain 负责组织 AI 调用逻辑
LLM       负责生成回答
```

### 今日任务

1. 安装依赖

```bash
pip install langchain langchain-openai python-dotenv
```

2. 配置环境变量

建议创建 `.env`：

```env
OPENAI_API_KEY=你的 API Key
```

3. 跑通第一个模型调用

练习内容：

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4o-mini")

response = model.invoke("用一句话解释 LangChain 是什么")
print(response.content)
```

4. 学习 Prompt

练习：

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个擅长解释技术概念的老师。"),
    ("human", "请解释：{topic}")
])

chain = prompt | model

response = chain.invoke({"topic": "FastAPI 和 LangChain 的关系"})
print(response.content)
```

5. 接入 FastAPI

新增接口：

```text
POST /ai/chat
```

请求示例：

```json
{
  "message": "什么是 LangChain？"
}
```

响应示例：

```json
{
  "answer": "..."
}
```

### 今日产出

你应该完成：

- 一个可以调用模型的 Python 文件
- 一个 Prompt Chain
- 一个 FastAPI AI 聊天接口

### 今日重点复盘

需要能回答：

1. LangChain 和 FastAPI 分别负责什么？
2. `model.invoke()` 返回的是什么？
3. `prompt | model` 表示什么？
4. 什么场景需要 PromptTemplate？

---

## 第 2 天：Tools 与 Agent

### 学习目标

让 AI 不只是回答问题，而是可以调用你写的 Python 函数，进一步调用你的任务数据库。

你需要掌握：

- Tool 是什么
- 如何把普通函数变成工具
- 工具参数说明的重要性
- Agent 是什么
- `create_agent` 的基本用法
- 如何让 AI 查询任务、创建任务

### 核心概念

Tool 可以理解为：

```text
提供给 AI 调用的函数
```

Agent 可以理解为：

```text
能根据用户问题，自己决定是否调用工具的 AI 流程
```

例如用户问：

```text
我还有哪些未完成任务？
```

Agent 应该能判断：

```text
这个问题需要查数据库 -> 调用查询任务工具 -> 总结结果
```

### 今日任务

1. 创建简单工具

示例：

```python
from langchain_core.tools import tool

@tool
def add(a: int, b: int) -> int:
    """计算两个整数的和。"""
    return a + b
```

2. 创建任务相关工具

建议先做两个工具：

```text
list_uncompleted_tasks
create_task_by_ai
```

示例设计：

```python
@tool
def list_uncompleted_tasks() -> str:
    """查询所有未完成任务，并返回任务摘要。"""
    ...
```

```python
@tool
def create_task_by_ai(title: str, description: str | None = None) -> str:
    """创建一个新任务。"""
    ...
```

3. 创建 Agent

示意：

```python
from langchain.agents import create_agent

agent = create_agent(
    model=model,
    tools=[list_uncompleted_tasks, create_task_by_ai],
    system_prompt="你是一个任务管理助手，可以帮助用户查询和创建任务。"
)
```

4. 接入 FastAPI

新增接口：

```text
POST /ai/tasks-assistant
```

请求示例：

```json
{
  "message": "我还有哪些未完成任务？"
}
```

另一个请求示例：

```json
{
  "message": "帮我创建一个任务：明天复习 FastAPI 测试。"
}
```

### 今日产出

你应该完成：

- 至少 2 个 LangChain Tool
- 一个能调用工具的 Agent
- 一个 FastAPI AI 任务助手接口

### 今日重点复盘

需要能回答：

1. Tool 和普通函数有什么区别？
2. Agent 为什么需要工具描述？
3. AI 是怎么决定调用哪个工具的？
4. 为什么工具不能随便暴露危险操作？

---

## 第 3 天：RAG 文档问答

### 学习目标

让 AI 基于你上传或提供的文档回答问题，而不是只依赖模型自身知识。

你需要掌握：

- RAG 是什么
- Document 是什么
- 文本切分
- Embedding
- 向量数据库
- Retriever
- 基于检索结果生成回答

### 核心概念

RAG 全称是 Retrieval-Augmented Generation，检索增强生成。

流程是：

```text
用户问题
  -> 向量检索相关文档片段
  -> 把片段和问题一起交给模型
  -> 模型基于文档生成答案
```

它解决的问题是：

```text
模型不知道你的私有文档
模型可能胡编
上下文太长不能全部塞进 prompt
```

### 今日任务

1. 准备文档

可以先用 `.txt` 或 `.md` 文件练习，暂时不用 PDF。

示例：

```text
docs/sample.md
```

2. 加载文档

学习文档加载器的基本思路。

3. 文本切分

理解为什么要切分：

```text
文档太长，需要切成多个小块方便检索
```

4. 生成 Embedding

理解 Embedding：

```text
把文本变成向量，用于相似度搜索
```

5. 建立本地向量库

可以使用轻量方案，例如 Chroma 或 FAISS。

6. 完成 RAG 问答

新增接口：

```text
POST /ai/rag
```

请求示例：

```json
{
  "question": "这份文档主要讲了什么？"
}
```

### 今日产出

你应该完成：

- 一个本地文档问答流程
- 一个向量检索器
- 一个 RAG FastAPI 接口

### 今日重点复盘

需要能回答：

1. RAG 为什么比直接问模型更可靠？
2. Embedding 是什么？
3. Retriever 返回的是什么？
4. 为什么文档要切分？
5. RAG 仍然可能出错的原因是什么？

---

## 第 4 天：项目整合、结构拆分与测试

### 学习目标

把前三天的 LangChain 代码整理进你的 FastAPI 项目中，形成一个较完整的 AI 后端项目。

### 推荐项目结构

在原有 FastAPI 项目基础上增加：

```text
app/
  main.py
  database.py
  models.py
  schemas.py
  crud.py
  routers/
    tasks.py
    ai.py
  ai/
    __init__.py
    models.py
    prompts.py
    chains.py
    tools.py
    agents.py
    rag.py
```

职责建议：

```text
app/routers/ai.py   AI 相关接口
app/ai/models.py    LLM 初始化
app/ai/prompts.py   Prompt 模板
app/ai/chains.py    普通 Chain
app/ai/tools.py     Agent 工具
app/ai/agents.py    Agent 组装
app/ai/rag.py       RAG 检索问答逻辑
```

### 今日任务

1. 拆分 AI 路由

新增：

```text
app/routers/ai.py
```

接口：

```text
POST /ai/chat
POST /ai/tasks-assistant
POST /ai/rag
```

2. 抽离模型初始化

例如：

```python
# app/ai/models.py
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")
```

3. 抽离 Prompt

例如：

```python
# app/ai/prompts.py
from langchain_core.prompts import ChatPromptTemplate

chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个简洁、准确的 AI 助手。"),
    ("human", "{message}")
])
```

4. 抽离工具和 Agent

把任务查询、任务创建工具放进：

```text
app/ai/tools.py
```

把 Agent 创建逻辑放进：

```text
app/ai/agents.py
```

5. 编写基础测试

新增测试：

```text
tests/test_ai.py
```

测试内容：

```text
/ai/chat 能返回 200
/ai/tasks-assistant 能处理基础输入
/ai/rag 缺少文档时能返回合理错误
```

注意：真实模型调用测试可能消耗费用，所以可以先用 mock 或只做轻量测试。

6. 写 README

补充：

```text
如何配置 API Key
如何启动服务
如何运行测试
有哪些 AI 接口
```

### 今日产出

你应该完成：

- 一个结构化 AI 后端项目
- AI 聊天接口
- AI 任务助手接口
- RAG 问答接口
- 基础测试
- README 文档

---

## 每天时间建议

如果每天 4 小时：

```text
30 分钟：概念讲解
2 小时：跟写代码
1 小时：自己扩展练习
30 分钟：复盘和整理笔记
```

如果每天 6 小时：

```text
1 小时：概念与示例
3 小时：项目实战
1 小时：调试与测试
1 小时：复盘与优化
```

---

## 学完后的能力清单

完成 4 天后，你应该能够：

- 使用 LangChain 调用大模型
- 编写 Prompt 和 Chain
- 使用 Tool 暴露 Python 函数给 AI
- 创建基础 Agent
- 让 Agent 调用 FastAPI 项目中的数据库能力
- 构建基础 RAG 文档问答
- 把 LangChain 集成进 FastAPI 项目结构
- 编写基础接口测试
- 判断什么时候需要 LangGraph

---

## 暂时不必深挖

4 天内不建议深挖这些内容：

- 复杂多 Agent 协作
- LangGraph 高级状态机
- 多轮长期记忆系统
- 企业级权限系统
- 大规模向量数据库调优
- 复杂评测体系
- 高并发流式输出优化

这些都很重要，但不适合一开始就塞进 4 天计划里。

---

## 推荐最终项目

项目名：AI Task Assistant

功能：

```text
1. 普通 AI 聊天
2. AI 查询未完成任务
3. AI 创建任务
4. 上传文档
5. 基于文档问答
6. FastAPI 暴露接口
7. pytest 基础测试
```

推荐接口：

```text
POST /ai/chat
POST /ai/tasks-assistant
POST /ai/rag
POST /upload
GET  /tasks
POST /tasks
```

这个项目能把你前面学过的 FastAPI、SQLAlchemy、文件上传、测试和 LangChain 串起来，是非常适合作为阶段作品的小项目。
