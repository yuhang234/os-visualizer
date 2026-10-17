"""本地部署方案（Ollama / LM Studio / llama.cpp / vLLM）探测与接入。

设计文档第 9.3 节：
- Ollama 默认端口 11434，OpenAI 端点 http://localhost:11434/v1，探测接口 GET /api/tags
- LM Studio 端口 1234、llama.cpp server 端口 8080、vLLM 端口 8000

探测一律使用短超时 + 明确错误码，不阻塞主事件循环。
"""

from __future__ import annotations

from typing import Any

import httpx

from ..core.config import settings

LOCAL_RUNTIMES: list[dict[str, Any]] = [
    {
        "key": "ollama",
        "name": "Ollama",
        "defaultPort": 11434,
        "baseUrl": "http://localhost:11434/v1",
        "nativeBase": "http://localhost:11434",
        "probePath": "/api/tags",
        "modelsPath": "models",
        "modelNameField": "name",
        "preferred": True,
        "installHint": "https://ollama.com/download",
    },
    {
        "key": "lmstudio",
        "name": "LM Studio",
        "defaultPort": 1234,
        "baseUrl": "http://localhost:1234/v1",
        "nativeBase": "http://localhost:1234",
        "probePath": "/v1/models",
        "modelsPath": "data",
        "modelNameField": "id",
        "preferred": False,
        "installHint": "https://lmstudio.ai/",
    },
    {
        "key": "llamacpp",
        "name": "llama.cpp server",
        "defaultPort": 8080,
        "baseUrl": "http://localhost:8080/v1",
        "nativeBase": "http://localhost:8080",
        "probePath": "/v1/models",
        "modelsPath": "data",
        "modelNameField": "id",
        "preferred": False,
        "installHint": "https://github.com/ggml-org/llama.cpp",
    },
    {
        "key": "vllm",
        "name": "vLLM",
        "defaultPort": 8000,
        "baseUrl": "http://localhost:8000/v1",
        "nativeBase": "http://localhost:8000",
        "probePath": "/v1/models",
        "modelsPath": "data",
        "modelNameField": "id",
        "preferred": False,
        "installHint": "https://docs.vllm.ai/",
    },
]

RUNTIME_BY_KEY: dict[str, dict[str, Any]] = {item["key"]: item for item in LOCAL_RUNTIMES}


def list_local_runtimes() -> list[dict[str, Any]]:
    return [dict(item) for item in LOCAL_RUNTIMES]


def _extract_models(payload: Any, runtime: dict[str, Any]) -> list[str]:
    models: list[str] = []
    if isinstance(payload, dict):
        container = payload.get(runtime["modelsPath"])
        if isinstance(container, list):
            for entry in container:
                if isinstance(entry, dict):
                    name = entry.get(runtime["modelNameField"])
                    if isinstance(name, str) and name:
                        models.append(name)
                elif isinstance(entry, str):
                    models.append(entry)
    return models


async def probe_runtime(runtime_key: str, *, host: str = "localhost", port: int | None = None) -> dict[str, Any]:
    """探测单个本地推理服务。返回结构固定，前端可直接渲染诊断卡片。"""
    runtime = RUNTIME_BY_KEY.get(runtime_key)
    if runtime is None:
        return {
            "key": runtime_key,
            "online": False,
            "errorCode": "UNKNOWN_RUNTIME",
            "error": f"未知的本地部署方案: {runtime_key}",
            "models": [],
        }
    actual_port = port or runtime["defaultPort"]
    native_base = f"http://{host}:{actual_port}"
    url = f"{native_base}{runtime['probePath']}"
    timeout = settings.local_probe_timeout
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            return {
                "key": runtime_key,
                "name": runtime["name"],
                "online": False,
                "url": url,
                "baseUrl": f"{native_base}/v1",
                "port": actual_port,
                "errorCode": f"HTTP_{response.status_code}",
                "error": f"探测接口返回 {response.status_code}",
                "models": [],
            }
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return {
            "key": runtime_key,
            "name": runtime["name"],
            "online": True,
            "url": url,
            "baseUrl": f"{native_base}/v1",
            "port": actual_port,
            "latencyMs": round(response.elapsed.total_seconds() * 1000, 1),
            "models": _extract_models(payload, runtime),
            "errorCode": None,
            "error": None,
        }
    except httpx.TimeoutException:
        return {
            "key": runtime_key,
            "name": runtime["name"],
            "online": False,
            "url": url,
            "baseUrl": f"{native_base}/v1",
            "port": actual_port,
            "errorCode": "TIMEOUT",
            "error": f"连接超时（{timeout}s），服务未启动或端口未监听",
            "models": [],
        }
    except httpx.ConnectError as exc:
        return {
            "key": runtime_key,
            "name": runtime["name"],
            "online": False,
            "url": url,
            "baseUrl": f"{native_base}/v1",
            "port": actual_port,
            "errorCode": "CONNECT_ERROR",
            "error": f"无法建立连接：{exc}",
            "models": [],
        }
    except httpx.HTTPError as exc:  # pragma: no cover - 网络层异常兜底
        return {
            "key": runtime_key,
            "name": runtime["name"],
            "online": False,
            "url": url,
            "baseUrl": f"{native_base}/v1",
            "port": actual_port,
            "errorCode": "NETWORK_ERROR",
            "error": str(exc),
            "models": [],
        }


async def detect_all_runtimes() -> list[dict[str, Any]]:
    import asyncio

    results = await asyncio.gather(
        *(probe_runtime(runtime["key"]) for runtime in LOCAL_RUNTIMES),
        return_exceptions=False,
    )
    return list(results)


async def list_ollama_models() -> list[str]:
    result = await probe_runtime("ollama")
    return result.get("models", []) if result.get("online") else []
