import os


# RAG 的 Embedding 模型已下载到本地缓存。测试时禁止 Hugging Face
# 再次检查远程元数据，避免网络波动导致 pytest 在收集阶段失败。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
