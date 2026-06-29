from pathlib import Path

from langchain_core.documents import Document


def load_text_document(file_path: str) -> list[Document]:
    path = Path(file_path)

    return [
        Document(
            page_content=path.read_text(encoding="utf-8"),
            metadata={"source": str(path)},
        )
    ]


documents = load_text_document("docs/agentchat-guide.md")

print("文档数量：", len(documents))
print("正文：")
print(documents[0].page_content)
print("元数据：", documents[0].metadata)