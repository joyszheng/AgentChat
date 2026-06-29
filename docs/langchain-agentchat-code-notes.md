# AgentChat LangChain 代码速查手册

本文档对应当前 `D:\project\AgentChat` 项目，用于忘记代码写法、关键参数或启动方式时快速查询。

## 1. 当前功能与文件位置

```text
backend/
├─ app/
│  ├─ main.py                 FastAPI 主程序
│  ├─ routers/ai.py           AI 接口：聊天、任务助手、RAG
│  ├─ ai_tools.py             查询任务、创建任务 Tool
│  ├─ rag.py                  文档加载、切分、检索、问答
│  ├─ database.py             SQLAlchemy 数据库连接
│  ├─ crud.py                 数据库 CRUD
│  ├─ models.py               ORM 模型
│  └─ schemas.py              Pydantic 模型
├─ docs/
│  └─ agentchat-guide.md      RAG 知识文档
├─ .env                       API Key，不要提交到 Git
└─ test.db                    SQLite 数据库
```

当前 AI 接口：

| 接口 | 作用 | 请求字段 |
|---|---|---|
| `POST /ai/chat` | 普通聊天 | `message` |
| `POST /ai/tasks-assistant` | 查询或创建任务 | `message` |
| `POST /ai/rag` | 根据文档回答问题 | `question` |

## 2. 环境变量与模型配置

`.env`：

```env
GLM_API_KEY=你的密钥
```

加载环境变量必须调用函数，不能漏掉括号：

```python
from dotenv import load_dotenv

load_dotenv()
```

错误写法：

```python
load_dotenv
```

当前聊天模型配置：

```python
model = ChatOpenAI(
    model="z-ai/glm-5.1",
    base_url="https://ai.hybgzs.com/v1",
    api_key=os.environ["GLM_API_KEY"],
    timeout=30,
)
```

关键参数：

| 参数 | 含义 | 注意事项 |
|---|---|---|
| `model` | 网关中的模型名称 | 必须与服务商提供的名称完全一致 |
| `base_url` | OpenAI 兼容接口地址 | 通常应以 `/v1` 结尾，按服务商说明填写 |
| `api_key` | API 密钥 | 从环境变量读取，不要写死在代码里 |
| `timeout=30` | 请求最长等待 30 秒 | 网络较慢时可适当调大 |

注意：`ChatOpenAI` 不代表只能调用 OpenAI 模型。只要服务提供 OpenAI 兼容协议，也可以接入 GLM、DeepSeek 等模型。

`.gitignore` 至少应包含：

```gitignore
.env
.venv/
__pycache__/
*.pyc
test.db
```

## 3. Prompt 与 Chain

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位简洁、准确、耐心的 AI 助手。"),
    ("human", "{message}"),
])

chain = prompt | model
response = chain.invoke({"message": "什么是 LangChain？"})
print(response.content)
```

需要记住：

- `{message}` 是模板变量，调用时必须提供同名字段。
- `prompt | model` 表示先生成消息，再调用模型。
- `invoke()` 返回的是消息对象，正文通常在 `response.content`。
- 字段名写错会导致验证错误，例如 `content` 不能写成 `contrnt`。

## 4. Tool

Tool 是提供给模型调用的 Python 函数。

```python
from langchain.tools import tool


@tool
def add(a: int, b: int) -> int:
    """计算并返回两个整数的和。"""
    return a + b
```

直接测试 Tool：

```python
result = add.invoke({"a": 3, "b": 5})
```

### Tool 最重要的三项信息

1. 函数名：模型用它识别工具。
2. 类型标注：模型据此生成参数。
3. 文档字符串：模型据此判断什么时候调用工具。

推荐文档字符串格式：

```python
@tool
def list_uncompleted_tasks(limit: int = 10) -> str:
    """查询数据库中的未完成任务。

    Args:
        limit: 最多返回多少条任务，默认返回 10 条。
    """
```

`Args:` 中应使用冒号，不建议写成 `limit = ...`。

### 数据库 Tool 的会话管理

```python
db = SessionLocal()

try:
    ...
finally:
    db.close()
```

必须写 `db.close()`，不能写成 `db.close`。后者只是引用方法，并没有关闭连接。

### 返回字符串时的常见错误

正确：

```python
f"描述：{task.description or '无'}"
```

错误：

```python
f"描述：{task, description or '无'}"
```

逗号会把表达式变成元组，输出类似 `(<Task object>, '描述')`。

### Tool 安全原则

- 查询工具相对安全。
- 创建、修改、删除属于有副作用操作。
- 只有用户意图明确时才允许 Agent 调用写操作工具。
- 不要直接暴露任意 SQL、文件删除或系统命令工具。
- Tool 返回的数据应清晰、简短、可供模型理解。

`limit=5` 只表示最多返回 5 条，不能据此声称数据库总共有 5 条。

## 5. Agent

Agent 会根据用户问题决定是否调用工具、调用哪个工具以及传什么参数。

```python
task_agent = create_agent(
    model=model,
    tools=[
        list_uncompleted_tasks,
        create_task_by_ai,
    ],
    system_prompt=(
        "你是任务管理助手。"
        "用户查询待办事项时，使用 list_uncompleted_tasks。"
        "用户明确要求创建任务时，使用 create_task_by_ai。"
        "意图不明确时不要创建任务，也不能编造数据库内容。"
        "工具返回的是指定数量以内的任务，不代表任务总数。"
    ),
)
```

调用 Agent：

```python
result = task_agent.invoke({
    "messages": [
        {
            "role": "user",
            "content": "查询前 5 条未完成任务",
        }
    ]
})

answer = result["messages"][-1].content
```

典型消息流程：

```text
HumanMessage
→ AIMessage（决定调用工具）
→ ToolMessage（工具执行结果）
→ AIMessage（最终回答）
```

调试工具调用：

```python
for message in result["messages"]:
    print(type(message).__name__, message.content)

    if getattr(message, "tool_calls", None):
        print(message.tool_calls)
```

## 6. RAG 总流程

```text
知识库构建：文档 → Document → Chunk → Embedding → VectorStore

问题回答：问题 → Retriever → 相关 Chunk → Prompt → 聊天模型 → 答案
```

RAG 不会训练模型，也不会修改模型参数。它只是在回答前为模型提供检索到的文档上下文。

### 6.1 Document

```python
document = Document(
    page_content=path.read_text(encoding="utf-8"),
    metadata={"source": str(path)},
)
```

- `page_content`：文档正文。
- `metadata`：文件名、来源、页码等附加信息。
- 文本文件必须明确使用 `encoding="utf-8"`。

不要继续使用已停止维护的 `langchain-community` `TextLoader`。简单的 `.txt`、`.md` 文件可以直接用 `Path.read_text()` 加载，再构造 `Document`。

### 6.2 稳定的文档路径

应用代码不要依赖当前终端目录：

```python
path = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "agentchat-guide.md"
)
```

这段代码从 `backend/app/rag.py` 定位到 `backend/docs/agentchat-guide.md`。

### 6.3 文本切分

```python
splitter = RecursiveCharacterTextSplitter(
    chunk_size=60,
    chunk_overlap=15,
)

chunks = splitter.split_documents([document])
```

| 参数 | 当前值 | 含义 |
|---|---:|---|
| `chunk_size` | `60` | 每个 Chunk 尽量不超过 60 个字符 |
| `chunk_overlap` | `15` | 相邻 Chunk 尽量保留 15 个字符的重叠 |

注意：重叠不是机械保证。切分器会优先保留自然段落，因此短文档可能看不到明显重复。

当前 `60/15` 是教学参数。真实中文文档可以从 `chunk_size=500`、`chunk_overlap=80` 开始测试，再根据检索效果调整。

### 6.4 Embedding

```python
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)
```

| 参数 | 含义 |
|---|---|
| `model_name` | 本地中文 Embedding 模型 |
| `device="cpu"` | 使用 CPU 推理，不依赖显卡 |
| `normalize_embeddings=True` | 归一化向量，便于余弦或点积相似度比较 |

当前模型生成 512 维向量。聊天模型与 Embedding 模型不是一回事：

- GLM：生成自然语言回答。
- BGE：把文本转换为向量，用于检索。

第一次运行会下载模型，之后通常从本地缓存加载。HF Token 警告不影响本地学习，只表示未认证请求的下载限额较低。

### 6.5 内存向量库

```python
vector_store = InMemoryVectorStore(embedding=embeddings)
vector_store.add_documents(documents=chunks)
```

内存向量库适合学习和小型测试：

- 优点：不需要额外部署数据库。
- 缺点：进程退出后数据消失，重启时需要重新建立索引。
- 数据量变大或需要持久化时，可换 Chroma、Qdrant、pgvector 等。

### 6.6 Retriever

```python
retriever = vector_store.as_retriever(
    search_kwargs={"k": 2}
)

documents = retriever.invoke(question)
```

`k=2` 表示返回两个最相关的 Chunk。`k` 太小可能漏掉答案，太大会增加无关上下文和模型费用。

Retriever 即使面对无答案问题，也通常会返回“相对最接近”的内容。因此必须通过 Prompt 约束模型不要猜测。

### 6.7 RAG Prompt

```python
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是文档问答助手。只能根据提供的文档内容回答。"
        "如果文档中没有答案，请明确回答：文档中没有相关信息。"
    ),
    (
        "human",
        "文档内容：\n{context}\n\n用户问题：{question}"
    ),
])
```

上下文拼接：

```python
context = "\n\n".join(
    doc.page_content
    for doc in documents
)
```

已知问题和未知问题都要测试：

```text
已知：AgentChat 的内部代号是什么？
预期：萤火虫 8868

未知：AgentChat 项目的负责人是谁？
预期：文档中没有相关信息。
```

## 7. 模块导入时不要调用远程模型

`app/rag.py` 可以在模块顶层建立文档索引，但不能在模块顶层保留测试调用：

```python
# 不要放在模块顶层
response = rag_chain.invoke(...)
```

因为 FastAPI 启动时会导入 `app.rag`。如果导入阶段就调用远程模型：

- 服务启动会被模型网络请求阻塞。
- 网关返回 503 时，整个 FastAPI 都无法启动。
- `--reload` 可能重复执行调用。

正确做法是封装函数，并只在接口请求到来时调用：

```python
def ask_document(question: str) -> tuple[str, list[str]]:
    documents = retriever.invoke(question)
    context = "\n\n".join(doc.page_content for doc in documents)
    response = rag_chain.invoke({"context": context, "question": question})
    sources = sorted({
        doc.metadata.get("source", "未知来源")
        for doc in documents
    })
    return response.content, sources
```

## 8. FastAPI 启动与测试

必须先进入后端目录：

```bash
cd D:\project\AgentChat\backend
```

推荐启动命令：

```bash
python -m uvicorn app.main:app --reload
```

也可以：

```bash
fastapi dev app/main.py
```

不要使用：

```bash
python app/main.py
```

原因：`app/main.py` 使用了 `from . import models` 等包内相对导入，直接作为脚本运行时没有父包，会出现：

```text
ImportError: attempted relative import with no known parent package
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

### 请求示例

普通聊天：

```json
{
  "message": "什么是 LangChain？"
}
```

任务查询：

```json
{
  "message": "查询前 5 条未完成任务"
}
```

任务创建：

```json
{
  "message": "创建任务，标题是复习 LangChain"
}
```

RAG：

```json
{
  "question": "AgentChat 的内部代号是什么？"
}
```

## 9. FastAPI 参数校验

```python
class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
```

- `min_length=1`：拒绝空字符串。
- `max_length=2000`：避免输入无限增大。
- `response_model`：约束和记录接口响应结构。

当前接口异常会打印完整堆栈，并向客户端返回简短错误：

```python
except Exception:
    traceback.print_exc()
    raise HTTPException(
        status_code=500,
        detail="文档问答服务暂时不可用",
    )
```

开发环境打印堆栈方便排错；生产环境应使用正式日志，并避免向客户端暴露密钥、绝对路径或内部错误详情。

## 10. 常见报错速查

### `KeyError: GLM_API_KEY`

检查：

- `.env` 是否在启动目录或可被找到的位置。
- 是否写了 `load_dotenv()`。
- 环境变量名是否完全一致。

### `attempted relative import with no known parent package`

不要运行 `python app/main.py`，改用：

```bash
python -m uvicorn app.main:app --reload
```

### `c10.dll` / `WinError 1114`

这是 PyTorch 的 Windows DLL 加载问题，不是 LangChain 代码错误。

处理顺序：

1. 安装或修复最新版 Microsoft Visual C++ Redistributable x64。
2. 重新打开终端或按提示重启电脑。
3. 测试：

```bash
python -c "import torch; print(torch.__version__); print(torch.rand(2))"
```

4. 仍失败时再考虑重装 CPU 版 PyTorch。

### Hugging Face 未认证警告

```text
Warning: You are sending unauthenticated requests to the HF Hub
```

这通常不是错误。本地学习可以忽略；频繁下载或达到限额时再配置 `HF_TOKEN`。

### 模型网关 `503 no available channels`

说明当前模型通道暂时不可用，通常不是代码语法错误。

- 稍后重试。
- 检查模型名和网关状态。
- 不要在模块导入阶段调用模型，否则 503 会阻止整个服务启动。

### `langchain-community` 弃用警告

`langchain-community` 已停止维护。本项目中的简单文本加载使用：

```python
Path(...).read_text(encoding="utf-8")
```

文本切分使用独立包：

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter
```

Embedding 使用独立包：

```python
from langchain_huggingface import HuggingFaceEmbeddings
```

## 11. 当前代码还可以改进的地方

1. `routers/ai.py` 中关于 DeepSeek 的注释已与当前 GLM 配置不一致，应改成“OpenAI 兼容模型”。
2. `sources` 当前返回服务器绝对路径，生产环境建议只返回文件名：

```python
sources = sorted({
    Path(doc.metadata.get("source", "未知来源")).name
    for doc in documents
})
```

3. 聊天与 RAG 分别创建了 `ChatOpenAI` 客户端，后续可抽离到统一的 `app/ai/models.py`。
4. `rag.py` 在导入阶段加载 Embedding 和建立索引，启动会较慢；后续可使用缓存或应用生命周期管理。
5. 当前向量库不持久化。需要持久化时再换 Chroma、Qdrant 或 pgvector。
6. 当前异常统一返回 500；上游模型不可用更适合返回 502 或 503。
7. 创建任务属于写操作，生产环境应增加身份验证、权限控制和必要的确认步骤。

## 12. 最终检查清单

启动前：

- [ ] 已激活 `.venv`
- [ ] `.env` 中存在 `GLM_API_KEY`
- [ ] 从 `backend` 目录启动
- [ ] `docs/agentchat-guide.md` 存在
- [ ] `python -c "import torch"` 不报错

功能验证：

- [ ] `/ai/chat` 能正常回答
- [ ] `/ai/tasks-assistant` 能查询任务
- [ ] `/ai/tasks-assistant` 能创建任务
- [ ] `/ai/rag` 能回答文档中存在的问题
- [ ] `/ai/rag` 对文档中不存在的信息不编造
- [ ] 代码中没有硬编码 API Key
- [ ] 模块顶层没有测试用的远程模型调用

