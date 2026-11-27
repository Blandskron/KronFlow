import logging
import re

from app.infrastructure.llm.pii_scrubber import is_valid_chilean_rut

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RUT_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,2}\.?\d{3}\.?\d{3}-[\dkK])(?![A-Za-z0-9])")
BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)


def sanitize_log_text(text: str) -> str:
    masked = BEARER_RE.sub("Bearer [REDACTED_TOKEN]", text)
    masked = EMAIL_RE.sub("[REDACTED_EMAIL]", masked)
    masked = RUT_RE.sub(lambda m: "[REDACTED_RUT]" if is_valid_chilean_rut(m.group(1)) else m.group(1), masked)
    return masked


class PiiRedactingLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            record.msg = sanitize_log_text(rendered)
            record.args = ()
        except Exception:
            pass
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    if not any(isinstance(f, PiiRedactingLogFilter) for f in root.filters):
        root.addFilter(PiiRedactingLogFilter())
