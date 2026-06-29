"""Cryptographic helpers for local authentication.

Password format: pbkdf2_sha256$210000$<salt_b64>$<hash_b64>
Token format:    secrets.token_urlsafe(48) — stored as SHA-256 hex in DB.

Rules enforced by validate_password_strength():
  - min 12 characters
  - at least one lowercase letter
  - at least one uppercase letter
  - at least one digit
  - at least one non-alphanumeric character (symbol)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from typing import Optional

_ITERATIONS = 210_000
_ALGO = "sha256"
_PREFIX = "pbkdf2_sha256"
_HASH_LEN = 32
_TOKEN_BYTES = 48

_RE_LOWER = re.compile(r"[a-z]")
_RE_UPPER = re.compile(r"[A-Z]")
_RE_DIGIT = re.compile(r"\d")
_RE_SYMBOL = re.compile(r"[^a-zA-Z0-9]")


def validate_password_strength(password: str) -> Optional[str]:
    """Return an error message if weak, or None if strong enough."""
    if len(password) < 12:
        return "La contraseña debe tener al menos 12 caracteres"
    if not _RE_LOWER.search(password):
        return "La contraseña debe contener al menos una letra minúscula"
    if not _RE_UPPER.search(password):
        return "La contraseña debe contener al menos una letra mayúscula"
    if not _RE_DIGIT.search(password):
        return "La contraseña debe contener al menos un número"
    if not _RE_SYMBOL.search(password):
        return "La contraseña debe contener al menos un símbolo"
    return None


def hash_password(password: str) -> str:
    """Return a salted PBKDF2-SHA256 hash string."""
    salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITERATIONS, dklen=_HASH_LEN)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(dk).decode("ascii")
    return f"{_PREFIX}${_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of password against stored hash string."""
    try:
        algo, iterations_s, salt_b64, hash_b64 = stored_hash.split("$")
    except ValueError:
        return False
    if algo != _PREFIX:
        return False
    try:
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, iterations, dklen=_HASH_LEN)
    return hmac.compare_digest(dk, expected)


def create_token() -> str:
    """Return a new random opaque token (clear — hand to caller, never log)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return SHA-256 hex digest of a clear token — this is what goes into DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, stored_hash: str) -> bool:
    """Constant-time comparison of a clear token against its stored hash."""
    return hmac.compare_digest(hash_token(token), stored_hash)


__all__ = [
    "validate_password_strength",
    "hash_password",
    "verify_password",
    "create_token",
    "hash_token",
    "verify_token",
]
