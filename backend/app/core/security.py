"""密码哈希与 JWT 签发/校验。

- 密码：PBKDF2-HMAC-SHA256，每用户独立随机盐，20 万次迭代（标准库实现，无额外依赖）。
- 令牌：JWT HS256，密钥来自环境变量或 data/jwt_secret.key（权限 600）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .config import settings

PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 32
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128


class AuthError(ValueError):
    """用户名或密码不符合规则。"""


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def validate_credentials(username: str, password: str) -> None:
    if not isinstance(username, str) or not isinstance(password, str):
        raise AuthError("用户名与密码必须为字符串")
    if len(username) < MIN_USERNAME_LENGTH or len(username) > MAX_USERNAME_LENGTH:
        raise AuthError(f"用户名长度需在 {MIN_USERNAME_LENGTH}~{MAX_USERNAME_LENGTH} 个字符之间")
    if not all(ch.isalnum() or ch in "_-." for ch in username):
        raise AuthError("用户名只能包含字母、数字、下划线、连字符与点")
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"密码长度需在 {MIN_PASSWORD_LENGTH}~{MAX_PASSWORD_LENGTH} 位之间")


def create_access_token(user_id: int, username: str) -> tuple[str, int]:
    expire_seconds = settings.jwt_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expire_seconds)).timestamp()),
        "iss": "os-visualizer",
    }
    token = jwt.encode(payload, settings.resolved_jwt_secret(), algorithm=settings.jwt_algorithm)
    return token, expire_seconds


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.resolved_jwt_secret(),
        algorithms=[settings.jwt_algorithm],
        issuer="os-visualizer",
    )
