from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class ChatCompletionPort:
    def complete(self, messages: list[ChatMessage]) -> str:
        raise NotImplementedError


class EmbeddingPort:
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError
