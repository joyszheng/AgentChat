import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    # model="z-ai/glm-5.1",
    model="qwen/qwen3.5-122b-a10b",
    # model="moonshotai/kimi-k2.6",
    base_url="https://ai.hybgzs.com/v1",
    api_key=os.environ["GLM_API_KEY"],
    timeout=30,
)