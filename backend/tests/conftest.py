"""pytest 全局夹具。

关键点：必须在导入 `app.*` 之前把数据目录、模型目录、JWT 密钥指向临时位置，
否则 `app.core.config` 会在仓库 `backend/data/` 下落盘真实数据。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="osvis-tests-"))

os.environ["OSVIS_DATA_DIR"] = str(_TMP_ROOT / "data")
os.environ["OSVIS_MODELS_DIR"] = str(_TMP_ROOT / "models_cache")
os.environ["OSVIS_JWT_SECRET"] = "unit-test-secret-do-not-use-in-production"
os.environ["OSVIS_GUEST_DAILY_CHAT_LIMIT"] = "2"
os.environ["OSVIS_SERVER_API_KEY"] = ""
os.environ["OSVIS_SERVER_BASE_URL"] = ""
os.environ["OSVIS_MOCK_CHUNK_DELAY"] = "0"  # 测试里不要真的等打字机延迟
# 测试专用：允许下载器访问本机回环地址，以便用本地 HTTP 服务器验证下载/续传状态机。
# 生产默认白名单不含 127.0.0.1（见 core/config.py），该覆盖只存在于测试环境变量中。
os.environ["OSVIS_DOWNLOAD_ALLOW_HOSTS"] = "127.0.0.1,localhost"
os.environ["OSVIS_DOWNLOAD_CHUNK_SIZE"] = str(16 * 1024)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP_ROOT
