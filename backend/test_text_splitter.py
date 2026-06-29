from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


path = Path("docs/agentchat-guide.md")

document = Document(
    page_content=path.read_text(encoding="utf-8"),
    metadata={"source": str(path)},
)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=60,
    chunk_overlap=15,
    length_function=len,
)

chunks = splitter.split_documents([document])

print("切分数量：", len(chunks))

for index, chunk in enumerate(chunks, start=1):
    print(f"\n--- Chunk {index} ---")
    print("长度：", len(chunk.page_content))
    print("正文：", chunk.page_content)
    print("元数据：", chunk.metadata)