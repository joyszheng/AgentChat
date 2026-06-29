from pathlib import Path

from langchain_core.documents import Document


path = Path("docs/agentchat-guide.md")
content = path.read_text(encoding="utf-8")

document = Document(
    page_content=content,
    metadata={"source": str(path)},
)

print("正文：")
print(document.page_content)

print("\n元数据：")
print(document.metadata)