"""Application-level authenticated encryption (MultiFernet) and HMAC-SHA256 blind indexing (PRV-008)."""

import base64
from collections.abc import Sequence
import hashlib
import hmac

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import get_settings


ENCRYPTED_PREFIX = "enc:v1:"


def _normalize_key(raw: str) -> bytes:
    stripped = raw.strip()
    try:
        Fernet(stripped.encode("utf-8"))
        return stripped.encode("utf-8")
    except Exception:
        digest = hashlib.sha256(stripped.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def _resolve_keys(keys: Sequence[str] | None = None) -> list[bytes]:
    if keys is not None:
        raw_list = [k.strip() for k in keys if k and k.strip()]
    else:
        configured = get_settings().app_encryption_keys or ""
        raw_list = [k.strip() for k in configured.split(",") if k.strip()]
    return [_normalize_key(k) for k in raw_list]


def _build_multi_fernet(keys: Sequence[str] | None = None) -> MultiFernet | None:
    resolved = _resolve_keys(keys)
    if not resolved:
        return None
    return MultiFernet([Fernet(k) for k in resolved])


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def encrypt_value(plaintext: str | None, *, keys: Sequence[str] | None = None) -> str | None:
    """Encrypt plaintext with primary Fernet key when configured; pass through if unconfigured."""
    if plaintext is None or plaintext == "":
        return plaintext
    if is_encrypted(plaintext):
        return plaintext
    mf = _build_multi_fernet(keys)
    if mf is None:
        return plaintext
    token = mf.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_value(stored: str | None, *, keys: Sequence[str] | None = None) -> str | None:
    """Decrypt enc:v1: ciphertext using MultiFernet (supports rotated keys) or return legacy plaintext."""
    if stored is None or not is_encrypted(stored):
        return stored
    mf = _build_multi_fernet(keys)
    if mf is None:
        raise RuntimeError("APP_ENCRYPTION_KEYS is required to decrypt stored ciphertext")
    token = stored[len(ENCRYPTED_PREFIX):].encode("ascii")
    return mf.decrypt(token).decode("utf-8")


def rotate_ciphertext(stored: str, *, keys: Sequence[str]) -> str:
    """Re-encrypt an existing enc:v1: ciphertext under the first (newest) key in `keys`."""
    if not is_encrypted(stored):
        result = encrypt_value(stored, keys=keys)
        return result if result is not None else stored
    mf = _build_multi_fernet(keys)
    if mf is None:
        raise ValueError("At least one encryption key is required for rotation")
    token = stored[len(ENCRYPTED_PREFIX):].encode("ascii")
    rotated = mf.rotate(token).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{rotated}"


def compute_blind_index(value: str, *, purpose: str = "rut", key: str | None = None) -> str:
    """Deterministic HMAC-SHA256 blind index for exact-match lookups on encrypted fields."""
    secret = (key or "").strip()
    if not secret:
        settings = get_settings()
        secret = (settings.app_blind_index_key or "").strip()
        if not secret:
            enc_keys = [k.strip() for k in (settings.app_encryption_keys or "").split(",") if k.strip()]
            secret = enc_keys[0] if enc_keys else "kronflow-local-blind-index"

    normalized = value.strip()
    if purpose == "rut":
        normalized = normalized.replace(".", "").replace(" ", "").upper()
    elif purpose == "email":
        normalized = normalized.lower()

    return hmac.new(
        secret.encode("utf-8"),
        f"{purpose}:{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
