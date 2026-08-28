"""
Password hashing, JWT creation/verification, and secure random token generation.

Notably absent: the scrypt-via-Node-builtin workaround and the n8n Code-node
sandbox restrictions we fought with earlier. passlib and python-jose are
first-class, well-tested libraries here — no platform sandbox to route around.
"""
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def generate_temp_password(length: int = 14) -> str:
    """Fully random characters, per the earlier decision — not word-based."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_secure_token(nbytes: int = 24) -> str:
    """For email verification links, approval links, and password reset links."""
    return secrets.token_hex(nbytes)


def create_access_token(user_id: uuid.UUID, jti: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    payload = {"sub": str(user_id), "jti": jti, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
