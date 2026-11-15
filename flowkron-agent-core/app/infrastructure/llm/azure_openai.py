from typing import Any

import httpx

from app.core.config import Settings
from app.domain.ports.llm import ChatMessage


class AzureOpenAIClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled_for_chat(self) -> bool:
        return bool(
            self.settings.azure_openai_enabled
            and self.settings.azure_openai_api_key
            and self.settings.chat_completion_url
        )

    @property
    def enabled_for_embeddings(self) -> bool:
        return bool(
            self.settings.azure_openai_enabled
            and self.settings.azure_openai_api_key
            and self.settings.embedding_url
        )

    def complete(self, messages: list[ChatMessage]) -> str:
        if not self.enabled_for_chat:
            raise RuntimeError("Azure OpenAI chat is not configured")
        payload: dict[str, Any] = {
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": self.settings.chat_completion_temperature,
            "max_tokens": self.settings.chat_completion_max_tokens,
        }
        headers = {"api-key": self.settings.azure_openai_api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=self.settings.chat_completion_timeout_seconds) as client:
            response = client.post(self.settings.chat_completion_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()

    def embed(self, text: str) -> list[float]:
        if not self.enabled_for_embeddings:
            raise RuntimeError("Azure OpenAI embeddings are not configured")
        payload = {"input": text, "model": self.settings.embedding_model_name}
        headers = {"api-key": self.settings.azure_openai_api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=self.settings.embedding_timeout_seconds) as client:
            response = client.post(self.settings.embedding_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return [float(value) for value in data["data"][0]["embedding"]]
