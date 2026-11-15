import httpx

from app.core.config import Settings
from app.domain.ports.llm import ChatMessage


class GroqClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled_for_chat(self) -> bool:
        return self.settings.chat_provider != "local" and bool(
            self.settings.groq_api_key.get_secret_value().strip()
        )

    def complete(self, messages: list[ChatMessage]) -> str:
        if not self.enabled_for_chat:
            raise RuntimeError("Groq chat is not configured")

        with httpx.Client(timeout=self.settings.chat_completion_timeout_seconds) as client:
            response = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key.get_secret_value()}"},
                json={
                    "model": self.settings.groq_model,
                    "messages": [{"role": message.role, "content": message.content} for message in messages],
                    "temperature": self.settings.chat_completion_temperature,
                    "max_completion_tokens": self.settings.chat_completion_max_tokens,
                },
            )
            response.raise_for_status()
            try:
                content = response.json()["choices"][0]["message"]["content"]
            except (IndexError, KeyError, TypeError, ValueError):
                raise RuntimeError("Groq returned an invalid completion") from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Groq returned an empty completion")
        return content.strip()
