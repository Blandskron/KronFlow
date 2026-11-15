from app.core.config import Settings
from app.infrastructure.llm.azure_openai import AzureOpenAIClient
from app.infrastructure.llm.groq import GroqClient


def chat_client(settings: Settings) -> AzureOpenAIClient | GroqClient | None:
    if settings.chat_provider == "local":
        return None
    groq = GroqClient(settings)
    if settings.chat_provider == "groq" or (
        settings.chat_provider == "auto" and groq.enabled_for_chat
    ):
        return groq
    return AzureOpenAIClient(settings)
