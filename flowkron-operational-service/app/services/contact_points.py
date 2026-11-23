import re


_EMAIL_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_EMAIL_LOCAL = re.compile(rf"{_EMAIL_ATOM}(?:\.{_EMAIL_ATOM})*")
_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_INTERNATIONAL_PHONE = re.compile(r"\+[0-9]+(?:[ .-]+[0-9]+|[ .-]*\([0-9]+\)[ .-]*[0-9]+)*")


def normalize_email(value: str | None) -> str | None:
    """Canonicalize a simple mailbox while preserving the case and aliases of its local part."""
    if not value:
        return None
    address = value.strip()
    local, _, domain = address.partition("@")
    labels = domain.split(".")
    if len(address) > 254 or len(local) > 64 or not _EMAIL_LOCAL.fullmatch(local):
        return None
    if len(labels) < 2 or not all(_DOMAIN_LABEL.fullmatch(label) for label in labels):
        return None
    return f"{local}@{domain.lower()}"


def normalize_phone(value: str | None) -> str | None:
    """Return the international form only when the number has an explicit + prefix."""
    if not value:
        return None
    candidate = value.strip()
    if len(candidate) > 80 or not _INTERNATIONAL_PHONE.fullmatch(candidate) or "(0)" in candidate:
        return None
    digits = re.sub(r"[^0-9]", "", candidate)
    if digits.startswith("0") or not 2 <= len(digits) <= 15:
        return None
    return f"+{digits}"
