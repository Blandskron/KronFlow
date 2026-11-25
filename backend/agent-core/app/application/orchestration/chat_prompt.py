from collections.abc import Sequence

from app.domain.ports.llm import ChatInputBudgetExceeded, ChatMessage


def build_context_prompt(
    system: str, question: str, excerpts: Sequence[str], max_chars: int,
) -> tuple[list[ChatMessage], int]:
    """Keep the user question intact and include whole excerpts in retrieval order."""
    prefix = "Contexto:\n"
    suffix = f"\n\nPregunta:\n{question}"
    separator = "\n\n"
    remaining = max_chars - len(system) - len(prefix) - len(suffix)
    selected = []
    for excerpt in excerpts:
        size = len(excerpt) + (len(separator) if selected else 0)
        if not excerpt.strip() or size > remaining:
            break
        selected.append(excerpt)
        remaining -= size
    if not selected:
        raise ChatInputBudgetExceeded("No complete context excerpt fits the input budget")

    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=prefix + separator.join(selected) + suffix),
    ], len(selected)
