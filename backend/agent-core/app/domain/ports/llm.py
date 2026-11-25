from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class ChatInputBudgetExceeded(RuntimeError):
    """The configured provider input budget cannot accommodate the request."""


class ChatCompletionPort:
    def complete(self, messages: list[ChatMessage]) -> str:
        raise NotImplementedError


class EmbeddingPort:
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError
