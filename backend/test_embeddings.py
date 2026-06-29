from langchain_huggingface import HuggingFaceEmbeddings


embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

texts = [
    "AgentChat 项目的内部代号是萤火虫 8868。",
    "标题以重点开头的任务需要优先处理。",
    "团队每晚 21:30 整理未完成任务。",
]

document_vectors = embeddings.embed_documents(texts)
query_vector = embeddings.embed_query("这个项目的内部名称是什么？")

print("文档数量：", len(document_vectors))
print("向量维度：", len(query_vector))

for text, vector in zip(texts, document_vectors):
    similarity = sum(
        query_value * document_value
        for query_value, document_value in zip(query_vector, vector)
    )

    print(f"\n相似度：{similarity:.4f}")
    print("文本：", text)