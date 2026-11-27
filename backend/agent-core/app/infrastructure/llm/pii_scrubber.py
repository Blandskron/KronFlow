"""Pre-egress PII Scrubber / Pseudonymizer for external LLM and AI connectors (PRV-005).

Redacts/pseudonymizes:
- Valid Chilean RUT (Mod-11 verified, formatted or unformatted) -> [RUT_n]
- Email addresses -> [EMAIL_n]
- Payment card numbers (13-19 digits, Luhn verified) -> [CARD_n]
- Phone numbers (+56 / E.164 / Chilean mobile) -> [PHONE_n]
"""

from dataclasses import dataclass, field
import re
from typing import Any


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Chilean RUT: 7-8 digits (with optional dot separators) followed by - and [0-9Kk]
RUT_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,2}\.?\d{3}\.?\d{3}-[\dkK])(?![A-Za-z0-9])")
# Potential payment card numbers: 13-19 digits with optional spaces or hyphens
CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
# International E.164 (+56 9 8765 4321, +1-202-555-0138) or Chilean mobile (569XXXXXXXX / 9 XXXX XXXX)
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+[1-9]\d{0,2}[\s.-]?(?:\(?\d{1,4}\)?[\s.-]?){2,4}\d{2,4}|\b56\s?9\s?\d{4}[\s.-]?\d{4}\b|\b9[\s.-]\d{4}[\s.-]\d{4}\b)(?!\w)"
)


def is_valid_chilean_rut(candidate: str) -> bool:
    """Validate Chilean RUT using Modulo 11 check digit."""
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
    """Validate payment card number (13-19 digits) using the Luhn algorithm."""
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
    """Tracks consistent reversible placeholders within a single outbound request."""

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

        def _replace_email(match: re.Match[str]) -> str:
            return self.placeholder("EMAIL", match.group(0))

        def _replace_card(match: re.Match[str]) -> str:
            raw = match.group(0)
            if is_valid_luhn_pan(raw):
                return self.placeholder("CARD", raw)
            return raw

        def _replace_rut(match: re.Match[str]) -> str:
            raw = match.group(1)
            if is_valid_chilean_rut(raw):
                return self.placeholder("RUT", raw)
            return raw

        def _replace_phone(match: re.Match[str]) -> str:
            raw = match.group(0)
            digit_count = sum(ch.isdigit() for ch in raw)
            if 8 <= digit_count <= 15:
                return self.placeholder("PHONE", raw)
            return raw

        scrubbed = EMAIL_RE.sub(_replace_email, text)
        scrubbed = CARD_CANDIDATE_RE.sub(_replace_card, scrubbed)
        scrubbed = RUT_RE.sub(_replace_rut, scrubbed)
        scrubbed = PHONE_RE.sub(_replace_phone, scrubbed)
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

    def restore_text(self, text: str) -> str:
        restored = text
        for token, raw in self._reverse.items():
            restored = restored.replace(token, raw)
        return restored


def scrub_text(text: str) -> tuple[str, ScrubSession]:
    session = ScrubSession()
    return session.scrub_text(text), session


def scrub_payload(payload: Any) -> tuple[Any, ScrubSession]:
    session = ScrubSession()
    return session.scrub_value(payload), session
