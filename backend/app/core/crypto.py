"""API Key 落库加密。

安全要求（设计文档第 10.3 节 + 本任务 spec）：
- API Key 绝不出现在前端代码或浏览器可见的明文里；请求一律经后端代理转发。
- 密钥落库时必须加密，并且限定文件权限。

实现：Fernet（AES-128-CBC + HMAC-SHA256 认证加密），密钥由 data/secret.key 派生：
  data/secret.key  —— 32 字节随机主密钥，文件权限 0600，仅本机可读
  Fernet key       —— 由主密钥经 HKDF-SHA256 派生（salt 固定为应用标识，保证重启后可解密）
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_KEY_FILE_NAME = "secret.key"
_HKDF_SALT = b"os-visualizer::provider-secret::v1"
MASK_PREFIX = "sk-"
MASK_SUFFIX_LENGTH = 4


def _master_key_path():
    return settings.data_dir / _KEY_FILE_NAME


def _load_or_create_master_key() -> bytes:
    path = _master_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        raw = path.read_bytes()
        if len(raw) >= 32:
            return raw[:32]
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - 非 POSIX 文件系统
        pass
    return key


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    master = _load_or_create_master_key()
    derived = hashlib.pbkdf2_hmac("sha256", master, _HKDF_SALT, 100_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(plaintext: str) -> str:
    if plaintext == "":
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    if ciphertext == "":
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("密钥解密失败：密文损坏或主密钥已更换") from exc


def mask_secret(plaintext: str) -> str:
    """生成可安全展示的掩码，例如 sk-abc***wxyz。前端只允许拿到这个值。"""
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return "*" * len(plaintext)
    head = plaintext[:6] if plaintext.startswith(MASK_PREFIX) else plaintext[:3]
    tail = plaintext[-MASK_SUFFIX_LENGTH:]
    return f"{head}{'*' * 6}{tail}"


def harden_file_permissions(path) -> None:
    """把包含敏感数据的文件权限收紧到 0600。"""
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover
        pass
