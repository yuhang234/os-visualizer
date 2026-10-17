"""FastAPI 应用入口。

启动：
    cd backend && uvicorn app.main:app --reload --port 8000

设计文档第 13.1 节工程结构：`app/main.py` 负责装配路由、CORS、生命周期。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.v1 import ai_proxy, algorithms, auth, engine_manager
from .core import db
from .core.config import public_path_label, settings
from .local_models.downloader import manager as download_manager
from .local_models.runtime import runtime_manager

logger = logging.getLogger("osvis")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    download_manager.ensure_loaded()
    download_manager.attach_runtime_manager(runtime_manager)
    logger.info("os-visualizer 后端就绪：数据目录 %s，模型目录 %s", settings.data_dir, settings.models_dir)
    try:
        yield
    finally:
        await runtime_manager.shutdown()


app = FastAPI(
    title="os-visualizer API",
    description="操作系统核心原理可视化教学平台后端：算法轨迹、模型引擎代理、鉴权",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _jsonable(value: Any) -> Any:
    """pydantic 报错的 ctx 里可能带 ValueError 等非 JSON 对象，统一转成字符串。"""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """设计文档约定参数问题返回 400；FastAPI 默认 422，这里统一成契约里的 400。"""
    errors = _jsonable(exc.errors())
    first = errors[0] if errors else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    detail = f"参数校验失败：{location} {first.get('msg', '')}".strip()
    return JSONResponse(status_code=400, content={"code": 400, "message": detail, "detail": errors[:5]})


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(algorithms.router, prefix=settings.api_prefix)
app.include_router(ai_proxy.router, prefix=settings.api_prefix)
app.include_router(engine_manager.router, prefix=settings.api_prefix)


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, Any]:
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "status": "healthy",
            "app": settings.app_name,
            # 只给相对标签：服务器绝对路径不进入浏览器可见的明文（见 config.public_path_label）
            "dataDirLabel": public_path_label(settings.data_dir),
            "modelsDirLabel": public_path_label(settings.models_dir),
            "guestDailyChatLimit": settings.guest_daily_chat_limit,
        },
    }
