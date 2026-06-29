import os

# 从 .env 文件读取 API 密钥等本地环境变量，避免将敏感信息写入代码。
from dotenv import load_dotenv
# ChatPromptTemplate 用于组合系统提示词和用户提示词。
from langchain_core.prompts import ChatPromptTemplate
# ChatOpenAI 提供 OpenAI 兼容接口的聊天模型客户端，也可连接 DeepSeek 等服务。
from langchain_openai import ChatOpenAI

# 加载 backend/.env 中的 DEEPSEEK_API_KEY。
load_dotenv()

# 初始化 DeepSeek 聊天模型；DeepSeek 的接口兼容 OpenAI Chat Completions 格式。
model = ChatOpenAI(
    model="deepseek-v4-flash",
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=30,
)

# 定义提示词模板：system 消息约束回答风格，human 消息接收动态主题。
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位简洁、耐心的 Python 技术老师。"),
    ("human", "请用三句话解释：{topic}")
])

# 使用 LCEL 管道把提示词输出直接传给模型。
chain = prompt | model
# 注入 topic 变量并同步调用模型，得到 AIMessage 响应对象。
response = chain.invoke({"topic": "FastAPI 和 LangChain 的分工"})
# 输出模型返回的纯文本内容。
print(response.content)
