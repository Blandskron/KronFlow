"""Pre-egress PII Scrubber for external AI / remote MCP connectors (PRV-005)."""

from dataclasses import dataclass, field
import re
from typing import Any


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RUT_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,2}\.?\d{3}\.?\d{3}-[\dkK])(?![A-Za-z0-9])")
CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+[1-9]\d{0,2}[\s.-]?(?:\(?\d{1,4}\)?[\s.-]?){2,4}\d{2,4}|\b56\s?9\s?\d{4}[\s.-]?\d{4}\b|\b9[\s.-]\d{4}[\s.-]\d{4}\b)(?!\w)"
)


def is_valid_chilean_rut(candidate: str) -> bool:
    cleaned = candidate.replace(".", "").replace("-", "").upper()
    if len(cleaned) < 8 or len(cleaned) > 9:
        return False
    body, dv = cleaned[:-1], cleaned[-1]
    if not body.isdigit():
        return False
    total = 0
    factor = 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    expected = "0" if remainder == 11 else ("K" if remainder == 10 else str(remainder))
    return dv == expected


def is_valid_luhn_pan(candidate: str) -> bool:
    digits = [int(ch) for ch in candidate if ch.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    if len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for idx, digit in enumerate(digits):
        if idx % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


@dataclass
class ScrubSession:
    _forward: dict[tuple[str, str], str] = field(default_factory=dict)
    _reverse: dict[str, str] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def placeholder(self, kind: str, raw: str) -> str:
        key = (kind, raw)
        existing = self._forward.get(key)
        if existing is not None:
            return existing
        count = self._counters.get(kind, 0) + 1
        self._counters[kind] = count
        token = f"[{kind}_{count}]"
        self._forward[key] = token
        self._reverse[token] = raw
        return token

    @property
    def redaction_count(self) -> int:
        return len(self._reverse)

    def scrub_text(self, text: str) -> str:
        if not text:
            return text

        scrubbed = EMAIL_RE.sub(lambda m: self.placeholder("EMAIL", m.group(0)), text)
        scrubbed = CARD_CANDIDATE_RE.sub(
            lambda m: self.placeholder("CARD", m.group(0)) if is_valid_luhn_pan(m.group(0)) else m.group(0),
            scrubbed,
        )
        scrubbed = RUT_RE.sub(
            lambda m: self.placeholder("RUT", m.group(1)) if is_valid_chilean_rut(m.group(1)) else m.group(1),
            scrubbed,
        )
        scrubbed = PHONE_RE.sub(
            lambda m: self.placeholder("PHONE", m.group(0))
            if 8 <= sum(ch.isdigit() for ch in m.group(0)) <= 15
            else m.group(0),
            scrubbed,
        )
        return scrubbed

    def scrub_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.scrub_text(value)
        if isinstance(value, list):
            return [self.scrub_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.scrub_value(item) for item in value)
        if isinstance(value, dict):
            return {k: self.scrub_value(v) for k, v in value.items()}
        return value


def scrub_payload(payload: Any) -> tuple[Any, ScrubSession]:
    session = ScrubSession()
    return session.scrub_value(payload), session


HEALTH_SENSITIVE_RE = re.compile(
    r"\b(diagn[oó]stico|enfermedad|medicamento|isapre|fonasa|ficha\s+cl[ií]nica|cirug[ií]a|"
    r"alergia|embarazo|psiquiatr[ií]a|salud\s+mental|medical\s+record|diagnosis|prescription)\b",
    re.IGNORECASE,
)
MINOR_SENSITIVE_RE = re.compile(
    r"\b(menor\s+de\s+edad|tengo\s+1[0-7]\s+a[nñ]os|soy\s+menor|mi\s+hij[oa]\s+de\s+\d{1,2}\s+a[nñ]os|underage)\b",
    re.IGNORECASE,
)


def detect_sensitive_data(text: str) -> dict[str, Any]:
    """Detect special-category PII (health, payment cards, minors) to trigger human review (PRV-021)."""
    if not text:
        return {"has_sensitive_data": False, "categories": [], "requires_human_review": False}
    categories: list[str] = []
    if any(is_valid_luhn_pan(m.group(0)) for m in CARD_CANDIDATE_RE.finditer(text)):
        categories.append("financial_card")
    if HEALTH_SENSITIVE_RE.search(text):
        categories.append("health")
    if MINOR_SENSITIVE_RE.search(text):
        categories.append("minor")
    return {
        "has_sensitive_data": bool(categories),
        "categories": categories,
        "requires_human_review": bool(categories),
    }
