"""AI 模型配置服务，支持从数据库动态加载配置。"""

import logging
from functools import lru_cache

from sqlalchemy.orm import Session

from .models import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    get_embeddings,
    get_llm,
)
from ..services.config import get_config_service


logger = logging.getLogger("uvicorn.error")


def get_llm_from_config(db: Session):
    """从数据库配置创建 LLM 实例，回退到环境变量。

    Args:
        db: 数据库会话

    Returns:
        ChatOpenAI: LLM 实例
    """
    config_service = get_config_service(db)

    base_url = config_service.get(
        "llm_base_url",
        config_service.get("ai_base_url", LLM_BASE_URL),
    )
    api_key = config_service.get("llm_api_key", LLM_API_KEY)
    model = config_service.get(
        "llm_model",
        config_service.get("ai_model", LLM_MODEL),
    )

    logger.debug("[ai_config] LLM config: base_url=%s model=%s", base_url, model)

    return get_llm(base_url=base_url, api_key=api_key, model=model)


def get_embeddings_from_config(db: Session):
    """从数据库配置创建 Embeddings 实例，回退到环境变量。

    Args:
        db: 数据库会话

    Returns:
        OpenAIEmbeddings: Embeddings 实例
    """
    config_service = get_config_service(db)

    llm_base_url = config_service.get(
        "llm_base_url",
        config_service.get("ai_base_url", LLM_BASE_URL),
    )
    llm_api_key = config_service.get("llm_api_key", LLM_API_KEY)
    base_url = config_service.get("embedding_base_url", "") or llm_base_url or EMBEDDING_BASE_URL
    api_key = config_service.get("embedding_api_key", "") or llm_api_key or EMBEDDING_API_KEY
    model = config_service.get("embedding_model", EMBEDDING_MODEL)
    dimensions = config_service.get_int("agentchat_embedding_dimensions", EMBEDDING_DIMENSIONS)

    logger.debug("[ai_config] Embeddings config: base_url=%s model=%s dimensions=%s", base_url, model, dimensions)

    return _get_cached_embeddings(base_url, api_key, model, dimensions)


@lru_cache(maxsize=8)
def _get_cached_embeddings(
    base_url: str,
    api_key: str,
    model: str,
    dimensions: int,
):
    """Reuse an embeddings client until one of its independent settings changes."""
    return get_embeddings(
        base_url=base_url,
        api_key=api_key,
        model=model,
        dimensions=dimensions,
    )
