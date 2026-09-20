"""Phase 5B local authentication primitives: Argon2id password hashing and
opaque session tokens. No JWT, no client-trusted identity claim -- a session
token is a random high-entropy value; only its SHA-256 is ever persisted, so
a database read alone cannot impersonate a live session."""
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

# argon2-cffi's PasswordHasher defaults to Type ID (Argon2id).
_hasher = PasswordHasher()

SESSION_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
