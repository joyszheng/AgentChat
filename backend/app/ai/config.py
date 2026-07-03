"""AI 模型配置服务，支持从数据库动态加载配置。"""

import logging

from sqlalchemy.orm import Session

from .models import get_llm, get_embeddings, AI_BASE_URL, AI_API_KEY, AI_MODEL, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
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

    base_url = config_service.get("ai_base_url", AI_BASE_URL)
    api_key = config_service.get("glm_api_key", AI_API_KEY)
    model = config_service.get("ai_model", AI_MODEL)

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

    base_url = config_service.get("ai_base_url", AI_BASE_URL)
    api_key = config_service.get("glm_api_key", AI_API_KEY)
    model = config_service.get("embedding_model", EMBEDDING_MODEL)
    dimensions = config_service.get_int("agentchat_embedding_dimensions", EMBEDDING_DIMENSIONS)

    logger.debug("[ai_config] Embeddings config: base_url=%s model=%s dimensions=%s", base_url, model, dimensions)

    return get_embeddings(base_url=base_url, api_key=api_key, model=model, dimensions=dimensions)
