import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()

# 默认配置（可通过环境变量覆盖）
DEFAULT_AI_BASE_URL = "https://ai.hybgzs.com/v1"
DEFAULT_AI_MODEL = "moonshotai/kimi-k2.6"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"

AI_BASE_URL = os.getenv("AI_BASE_URL", DEFAULT_AI_BASE_URL)
AI_API_KEY = os.environ.get("GLM_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", DEFAULT_AI_MODEL)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
EMBEDDING_DIMENSIONS = int(os.getenv("AGENTCHAT_EMBEDDING_DIMENSIONS", "1024"))


def get_llm(*, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
    """获取 LLM 实例，支持动态配置覆盖。

    Args:
        base_url: API 基础地址，不传则使用默认配置
        api_key: API 密钥，不传则使用默认配置
        model: 模型名称，不传则使用默认配置

    Returns:
        ChatOpenAI: LLM 实例
    """
    return ChatOpenAI(
        model=model or AI_MODEL,
        base_url=base_url or AI_BASE_URL,
        api_key=api_key or AI_API_KEY,
        timeout=30,
        max_retries=2,
    )


def get_embeddings(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
):
    """获取 Embeddings 实例，支持动态配置覆盖。

    Args:
        base_url: API 基础地址，不传则使用默认配置
        api_key: API 密钥，不传则使用默认配置
        model: 模型名称，不传则使用默认配置
        dimensions: 向量维度，不传则使用默认配置

    Returns:
        OpenAIEmbeddings: Embeddings 实例
    """
    return OpenAIEmbeddings(
        model=model or EMBEDDING_MODEL,
        dimensions=dimensions or EMBEDDING_DIMENSIONS,
        base_url=base_url or AI_BASE_URL,
        api_key=api_key or AI_API_KEY,
        timeout=30,
        max_retries=2,
        tiktoken_enabled=False,
        check_embedding_ctx_length=False,
    )


# 保持向后兼容：默认实例
llm = get_llm()
embeddings = get_embeddings()
