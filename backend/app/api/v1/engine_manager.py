"""模型引擎管理接口：连通性探测、本地部署接入、内置小模型下载（设计文档第 9、10、13.2 节）。

接口清单：
    POST /api/v1/ai/engine/ping                 任意厂商 / 中转 base_url 连通性与延迟
    GET  /api/v1/ai/engine/local/detect         探测本机 Ollama / LM Studio / llama.cpp / vLLM
    POST /api/v1/ai/engine/local/connect        探测成功即保存为可用的本地引擎配置
    GET  /api/v1/ai/engine/models/catalog       4 款内置小模型静态清单
    GET  /api/v1/ai/engine/models/status        五态实时状态 + 下载进度
    GET  /api/v1/ai/engine/models/disk          磁盘占用统计
    POST /api/v1/ai/engine/models/download      触发下载（支持断点续传）
    POST /api/v1/ai/engine/models/pause|cancel|retry|delete|load|unload
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ...core import db
from ...core.config import public_path_label, settings
from ...core.crypto import decrypt_secret
from ...local_models.catalog import MODEL_BY_ID, list_models, total_download_bytes
from ...local_models.downloader import DownloadError, manager as download_manager
from ...local_models.runtime import RuntimeLoadError, runtime_manager
from ...providers.catalog import get_provider_template
from ...providers.client import ping_provider
from ...providers.local_runtimes import RUNTIME_BY_KEY, detect_all_runtimes, probe_runtime
from ...schemas.common import ok
from ...schemas.engine import LocalConnectRequest, ModelDownloadRequest, ModelIdRequest, PingRequest
from ..deps import current_user_optional

router = APIRouter(prefix="/ai/engine", tags=["engine"])

# 启动时即建立下载管理器 ↔ 运行时管理器的联系（幂等）
download_manager.attach_runtime_manager(runtime_manager)


# ---------------- 连通性探测 ----------------


@router.post("/ping")
async def ping(payload: PingRequest, user: dict[str, Any] | None = Depends(current_user_optional)) -> dict[str, Any]:
    """测试连接：返回往返延迟（ms），或带错误码的失败诊断。

    三种入参形态：已保存配置（providerId）、临时模板 + 用户填写的密钥、纯自定义 base_url。
    """
    user_id = user["id"] if user else None
    provider: dict[str, Any] | None = None
    api_key = payload.apiKey or ""

    if payload.providerId is not None:
        row = db.get_provider_config(payload.providerId, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="配置不存在或无权访问")
        provider = dict(get_provider_template(row["provider_key"]) or {"key": row["provider_key"]})
        try:
            extra = json.loads(row["extra_headers"] or "{}")
        except json.JSONDecodeError:
            extra = {}
        provider.setdefault("extraHeaders", {})
        provider["extraHeaders"] = {**provider["extraHeaders"], **extra}
        provider["baseUrl"] = payload.baseUrl or row["base_url"]
        model = payload.model or row["model"]
        if not api_key and not payload.apiKey:
            try:
                api_key = decrypt_secret(row["api_key_cipher"] or "")
            except ValueError as exc:
                return ok({"ok": False, "errorCode": "DECRYPT_FAILED", "error": str(exc)})
    else:
        if payload.providerKey:
            template = get_provider_template(payload.providerKey)
            if template is None:
                raise HTTPException(status_code=400, detail=f"未知的厂商模板: {payload.providerKey}")
            provider = dict(template)
        else:
            provider = {
                "key": "custom",
                "name": "自定义 / 中转 API",
                "authHeader": "Authorization",
                "authScheme": "Bearer",
                "extraHeaders": {},
                "openAiCompatible": True,
                "sseTextPath": "choices.0.delta.content",
            }
        if payload.baseUrl:
            provider["baseUrl"] = payload.baseUrl
        provider["extraHeaders"] = {**(provider.get("extraHeaders") or {}), **(payload.extraHeaders or {})}
        model = payload.model or provider.get("defaultModel", "")

    if not (provider.get("baseUrl") or "").strip():
        return ok({"ok": False, "errorCode": "NO_BASE_URL", "error": "请先填写 base_url"})

    result = await ping_provider(provider, api_key, model)
    return ok(result)


# ---------------- 本地部署 ----------------


@router.get("/local/detect")
async def local_detect() -> dict[str, Any]:
    """并发探测四类本地推理服务，返回每个方案的在线状态与已装载模型列表。"""
    results = await detect_all_runtimes()
    availability = await runtime_manager.runtime_availability()
    return ok({"runtimes": results, "loadingBackends": availability})


@router.post("/local/connect")
async def local_connect(
    payload: LocalConnectRequest,
    user: dict[str, Any] | None = Depends(current_user_optional),
) -> dict[str, Any]:
    """探测 + 一键接入：把本地推理服务保存为可用的引擎配置（API Key 留空）。"""
    if payload.runtimeKey not in RUNTIME_BY_KEY:
        raise HTTPException(status_code=400, detail=f"未知的本地部署方案: {payload.runtimeKey}")
    probe = await probe_runtime(payload.runtimeKey, host=payload.host, port=payload.port)
    if not probe.get("online"):
        return ok({"connected": False, "probe": probe}, message=f"{probe.get('name') or payload.runtimeKey} 未在线，无法接入")

    models: list[str] = list(probe.get("models") or [])
    chosen = payload.model.strip() or (models[0] if models else "")
    if not chosen:
        return ok(
            {"connected": False, "probe": probe},
            message="服务在线，但未探测到任何已拉取的模型；请先 `ollama pull qwen2.5:1.5b` 等命令准备模型",
        )

    if not payload.save:
        return ok({"connected": True, "probe": probe, "model": chosen, "saved": False})

    runtime = RUNTIME_BY_KEY[payload.runtimeKey]
    user_id = user["id"] if user else None
    display = f"{runtime['name']} 本地部署 ({chosen})"
    saved = db.upsert_provider_config(
        user_id=user_id,
        provider_key=payload.runtimeKey,
        display_name=display,
        base_url=probe.get("baseUrl") or runtime["baseUrl"],
        model=chosen,
        api_key_cipher="",  # 本地服务无需密钥
        extra_headers="{}",
        is_local=True,
    )
    db.set_active_provider(int(saved["id"]), user_id)
    return ok(
        {
            "connected": True,
            "probe": probe,
            "model": chosen,
            "saved": True,
            "configId": int(saved["id"]),
        },
        message=f"已接入 {runtime['name']}，模型 {chosen} 设为当前对话引擎",
    )


# ---------------- 内置小模型下载 ----------------


def _model_public_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """清单字段 + 下载地址（供前端展示来源；不含任何密钥）。"""
    return {**meta}


@router.get("/models/catalog")
def models_catalog() -> dict[str, Any]:
    return ok(
        {
            "models": [_model_public_meta(meta) for meta in list_models()],
            "totalBytes": total_download_bytes(),
            "states": ["NOT_DOWNLOADED", "DOWNLOADING", "READY", "LOADING", "ERROR"],
            "modelsDirLabel": public_path_label(settings.models_dir),
        }
    )


@router.get("/models/status")
def models_status() -> dict[str, Any]:
    return ok({"models": download_manager.status(), "disk": download_manager.disk_usage()})


@router.get("/models/disk")
def models_disk() -> dict[str, Any]:
    return ok(download_manager.disk_usage())


async def _action(fn, model_id: str) -> dict[str, Any]:
    try:
        return await fn(model_id)
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/download")
async def models_download(payload: ModelDownloadRequest) -> dict[str, Any]:
    if payload.modelId not in MODEL_BY_ID:
        raise HTTPException(status_code=404, detail=f"未知的内置模型: {payload.modelId}")
    try:
        task = await download_manager.start(payload.modelId, payload.sourceUrl)
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(task, message="下载任务已启动")


@router.post("/models/pause")
async def models_pause(payload: ModelIdRequest) -> dict[str, Any]:
    return ok(await _action(download_manager.pause, payload.modelId), message="已暂停，断点已保留")


@router.post("/models/cancel")
async def models_cancel(payload: ModelIdRequest) -> dict[str, Any]:
    return ok(await _action(download_manager.cancel, payload.modelId), message="已取消并清除断点文件")


@router.post("/models/retry")
async def models_retry(payload: ModelIdRequest) -> dict[str, Any]:
    return ok(await _action(download_manager.retry, payload.modelId), message="已重新开始下载（断点续传）")


@router.post("/models/delete")
async def models_delete(payload: ModelIdRequest) -> dict[str, Any]:
    return ok(await _action(download_manager.delete, payload.modelId), message="已删除本地模型文件")


@router.post("/models/load")
async def models_load(payload: ModelIdRequest) -> dict[str, Any]:
    try:
        result = await download_manager.load(payload.modelId)
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("errorCode") == "LOAD_FAILED":
        return ok(result, message=f"装载失败：{result.get('error')}")
    return ok(result, message=f"装载成功，运行后端 {result.get('loadedRuntime')}（模型名 {result.get('runtimeModel')}）")


@router.post("/models/unload")
async def models_unload(payload: ModelIdRequest) -> dict[str, Any]:
    return ok(await _action(download_manager.unload, payload.modelId), message="已卸载")
