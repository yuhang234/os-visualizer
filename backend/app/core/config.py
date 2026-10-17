"""运行时配置。

设计文档第 13 章约定：`backend/app/core/config.py` 负责环境变量与配置。
本模块刻意不引入 pydantic-settings，改为极简 .env 解析，减少运行时依赖面。
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def public_path_label(path: Path) -> str:
    """把服务端目录折叠成浏览器可见的安全标签。

    安全要求：API Key 与本地模型 / 数据目录的服务器绝对路径都不得出现在浏览器可见的明文里。
    因此对外接口只给出相对 `backend/` 的标签（自定义到工作区外的目录只暴露目录名）。
    """
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(BACKEND_DIR)
    except ValueError:
        return resolved.name or "."
    return f"backend/{relative.as_posix()}"


def _load_dotenv(path: Path) -> None:
    """把 .env 文件里的键值对注入 os.environ（不覆盖已存在的环境变量）。"""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BACKEND_DIR / ".env")


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """进程级配置。所有路径默认落在 backend/ 目录内，保证工作区自包含。"""

    app_name: str = "os-visualizer API"
    api_prefix: str = "/api/v1"

    # 数据落盘位置
    data_dir: Path = field(default_factory=lambda: Path(_env_str("OSVIS_DATA_DIR", str(BACKEND_DIR / "data"))))
    models_dir: Path = field(default_factory=lambda: Path(_env_str("OSVIS_MODELS_DIR", str(BACKEND_DIR / "models_cache"))))

    # 鉴权
    jwt_secret: str = field(default_factory=lambda: _env_str("OSVIS_JWT_SECRET", ""))
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = field(default_factory=lambda: _env_int("OSVIS_JWT_EXPIRE_MINUTES", 60 * 24 * 7))

    # 游客额度：使用服务端默认云端 Key 时，游客每日对话上限（自定义 Key / 本地部署不受限）
    guest_daily_chat_limit: int = field(default_factory=lambda: _env_int("OSVIS_GUEST_DAILY_CHAT_LIMIT", 5))

    # 服务端默认云端模型（无自定义配置时的兜底，需要环境变量提供 Key）
    default_provider: str = field(default_factory=lambda: _env_str("OSVIS_DEFAULT_PROVIDER", "deepseek"))
    default_model: str = field(default_factory=lambda: _env_str("OSVIS_DEFAULT_MODEL", "deepseek-chat"))
    server_api_key: str = field(default_factory=lambda: _env_str("OSVIS_SERVER_API_KEY", ""))
    server_base_url: str = field(default_factory=lambda: _env_str("OSVIS_SERVER_BASE_URL", ""))

    # 本地部署探测
    local_probe_timeout: float = field(default_factory=lambda: _env_float("OSVIS_LOCAL_PROBE_TIMEOUT", 2.5))

    # 下载管理器
    download_chunk_size: int = field(default_factory=lambda: _env_int("OSVIS_DOWNLOAD_CHUNK_SIZE", 256 * 1024))
    download_allow_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            h.strip()
            for h in _env_str(
                "OSVIS_DOWNLOAD_ALLOW_HOSTS",
                "huggingface.co,cdn-lfs.huggingface.co,cdn-lfs-us-1.huggingface.co,modelscope.cn,"
                "www.modelscope.cn,ollama.com,registry.ollama.ai,github.com,objects.githubusercontent.com",
            ).split(",")
            if h.strip()
        )
    )

    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env_str(
                "OSVIS_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
            ).split(",")
            if o.strip()
        )
    )

    def resolved_jwt_secret(self) -> str:
        """优先使用环境变量；未配置时读取/生成持久化密钥文件，避免重启后 Token 失效。"""
        if self.jwt_secret:
            return self.jwt_secret
        secret_file = self.data_dir / "jwt_secret.key"
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        if secret_file.is_file():
            value = secret_file.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(48)
        secret_file.write_text(value, encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except OSError:  # pragma: no cover - 非 POSIX 文件系统
            pass
        return value

    @property
    def db_path(self) -> Path:
        return self.data_dir / "osvis.sqlite3"


settings = Settings()

settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.models_dir.mkdir(parents=True, exist_ok=True)
