import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()

AI_BASE_URL = "https://ai.hybgzs.com/v1"
AI_API_KEY = os.environ["GLM_API_KEY"]
EMBEDDING_DIMENSIONS = int(os.getenv("AGENTCHAT_EMBEDDING_DIMENSIONS", "1024"))

llm = ChatOpenAI(
    # model="z-ai/glm-5.1",
    model="qwen/qwen3.5-122b-a10b",
    # model="moonshotai/kimi-k2.6",
    base_url=AI_BASE_URL,
    api_key=AI_API_KEY,
    timeout=30,
)

embeddings = OpenAIEmbeddings(
    model="Qwen/Qwen3-Embedding-8B",
    dimensions=EMBEDDING_DIMENSIONS,
    base_url=AI_BASE_URL,
    api_key=AI_API_KEY,
    timeout=30,
    tiktoken_enabled=False,
    check_embedding_ctx_length=False,
)
