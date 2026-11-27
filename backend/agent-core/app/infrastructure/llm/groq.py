from dataclasses import dataclass
import logging
from time import perf_counter

import httpx

from app.core.config import Settings
from app.domain.ports.llm import ChatInputBudgetExceeded, ChatMessage
from app.infrastructure.llm.pii_scrubber import ScrubSession


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompletionObservation:
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


def _observed_usage(data: dict) -> tuple[int, int, int] | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    counts = tuple(usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
    if any(type(count) is not int or count < 0 for count in counts):
        return None
    input_tokens, output_tokens, total_tokens = counts
    return (input_tokens, output_tokens, total_tokens) if input_tokens + output_tokens == total_tokens else None


def _observe(outcome: str, started: float, input_chars: int, usage: tuple[int, int, int] | None = None) -> None:
    input_tokens, output_tokens, total_tokens = usage if usage is not None else (None, None, None)
    logger.info(
        "chat_completion outcome=%s elapsed_ms=%.1f input_chars=%d input_tokens=%s output_tokens=%s total_tokens=%s",
        outcome, (perf_counter() - started) * 1000, input_chars, input_tokens, output_tokens, total_tokens,
    )


class GroqClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_observation: CompletionObservation | None = None

    @property
    def enabled_for_chat(self) -> bool:
        return self.settings.chat_provider != "local" and bool(
            self.settings.groq_api_key.get_secret_value().strip()
        )

    def complete(self, messages: list[ChatMessage]) -> str:
        if not self.enabled_for_chat:
            raise RuntimeError("Groq chat is not configured")

        self.last_observation = None
        started = perf_counter()
        input_chars = sum(len(message.content) for message in messages)
        if input_chars > self.settings.chat_input_max_chars:
            _observe("input_budget_exceeded", started, input_chars)
            raise ChatInputBudgetExceeded("Groq input budget exceeded")

        scrubber = ScrubSession()
        scrubbed_messages = [
            {"role": message.role, "content": scrubber.scrub_text(message.content)}
            for message in messages
        ]
        if scrubber.redaction_count:
            logger.info("chat_completion_pii_scrubbed redactions=%d", scrubber.redaction_count)

        try:
            with httpx.Client(timeout=self.settings.chat_completion_timeout_seconds) as client:
                response = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.groq_api_key.get_secret_value()}"},
                    json={
                        "model": self.settings.groq_model,
                        "messages": scrubbed_messages,
                        "temperature": self.settings.chat_completion_temperature,
                        "max_completion_tokens": self.settings.chat_completion_max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Empty completion")
        except httpx.HTTPError:
            _observe("provider_error", started, input_chars)
            raise
        except (IndexError, KeyError, TypeError, ValueError):
            _observe("invalid_completion", started, input_chars)
            raise RuntimeError("Groq returned an invalid completion") from None

        usage = _observed_usage(data)
        elapsed_ms = max(0, int(round((perf_counter() - started) * 1000)))
        self.last_observation = CompletionObservation(
            provider="groq",
            model=self.settings.groq_model,
            prompt_tokens=usage[0] if usage is not None else None,
            completion_tokens=usage[1] if usage is not None else None,
            latency_ms=elapsed_ms,
        )
        _observe("completed", started, input_chars, usage)
        return content.strip()
