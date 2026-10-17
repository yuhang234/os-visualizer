"""本地模型装载运行时：把下载好的 GGUF 接入可推理的后端。

设计文档 10.1 推荐加载后端为 Ollama / llama.cpp，10.2 中 LOADING 状态语义是
"模型正装载入内存 (mmap)"。本模块如实实现两条路径，并在两者都不可用时返回明确的
失败原因（绝不伪造"已加载"状态）：

1. Ollama（首选）：调用本机 Ollama 的 `POST /api/create` 把 GGUF 注册为本地模型，
   注册成功后即可通过 Ollama 的 OpenAI 兼容端点推理。
2. llama.cpp server：当环境变量 OSVIS_LLAMACPP_BIN 指向 llama-server 可执行文件时，
   由后端拉起子进程（mmap 加载），就绪后通过其 OpenAI 兼容端点推理。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from ..core.config import settings
from ..providers.local_runtimes import probe_runtime

# Ollama 注册后的模型名统一加前缀，避免与用户已有模型冲突
OLLAMA_MODEL_PREFIX = "osvis-"
LLAMACPP_READY_TIMEOUT = 60.0


class RuntimeLoadError(RuntimeError):
    """装载失败，附带可展示给用户的原因。"""


class LocalRuntimeManager:
    def __init__(self) -> None:
        self._llamacpp_processes: dict[str, asyncio.subprocess.Process] = {}
        self._loaded: dict[str, dict[str, Any]] = {}

    # ---------- 环境探测 ----------

    @staticmethod
    def _llamacpp_binary() -> str | None:
        configured = os.environ.get("OSVIS_LLAMACPP_BIN", "").strip()
        if configured:
            path = Path(configured).expanduser()
            return str(path) if path.is_file() else None
        return shutil.which("llama-server")

    async def runtime_availability(self) -> dict[str, Any]:
        ollama = await probe_runtime("ollama")
        binary = self._llamacpp_binary()
        return {
            "ollama": {"online": bool(ollama.get("online")), "error": ollama.get("error"), "models": ollama.get("models", [])},
            "llamacpp": {
                "binaryAvailable": binary is not None,
                "binaryPath": binary or "",
                "hint": "设置环境变量 OSVIS_LLAMACPP_BIN 指向 llama-server 可执行文件，或安装 llama.cpp 并加入 PATH",
            },
        }

    # ---------- 装载 ----------

    async def load(self, model_id: str, gguf_path: Path) -> dict[str, Any]:
        if not gguf_path.is_file():
            raise RuntimeLoadError(f"GGUF 文件不存在: {gguf_path}")
        errors: list[str] = []

        ollama = await probe_runtime("ollama")
        if ollama.get("online"):
            try:
                runtime_model = await self._register_ollama(model_id, gguf_path)
                result = {
                    "runtime": "ollama",
                    "runtimeModel": runtime_model,
                    "baseUrl": ollama.get("baseUrl", "http://localhost:11434/v1"),
                    "loadedAt": time.time(),
                }
                self._loaded[model_id] = result
                return result
            except RuntimeLoadError as exc:
                errors.append(f"Ollama: {exc}")
        else:
            errors.append(f"Ollama: 未检测到在线服务（{ollama.get('error') or '未启动'}）")

        binary = self._llamacpp_binary()
        if binary:
            try:
                runtime_model = await self._spawn_llamacpp(model_id, gguf_path, binary)
                result = {
                    "runtime": "llamacpp",
                    "runtimeModel": runtime_model,
                    "baseUrl": "http://localhost:8080/v1",
                    "loadedAt": time.time(),
                }
                self._loaded[model_id] = result
                return result
            except RuntimeLoadError as exc:
                errors.append(f"llama.cpp: {exc}")
        else:
            errors.append(
                "llama.cpp: 未找到 llama-server 可执行文件（可设置 OSVIS_LLAMACPP_BIN 或安装 llama.cpp）"
            )

        raise RuntimeLoadError(
            "无可用本地推理后端，模型无法装载。诊断：" + "；".join(errors)
            + "。建议安装 Ollama（https://ollama.com/download）后重试。"
        )

    async def _register_ollama(self, model_id: str, gguf_path: Path) -> str:
        runtime_model = f"{OLLAMA_MODEL_PREFIX}{model_id}"
        payload = {
            "model": runtime_model,
            "files": {gguf_path.name: str(gguf_path)},
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=600.0, write=30.0, pool=5.0)) as client:
                response = await client.post("http://localhost:11434/api/create", json=payload)
        except httpx.HTTPError as exc:
            raise RuntimeLoadError(f"注册 GGUF 失败：{exc}") from exc
        if response.status_code >= 400:
            detail = response.text[:300]
            raise RuntimeLoadError(f"注册 GGUF 失败（HTTP {response.status_code}）：{detail}")
        return runtime_model

    async def _spawn_llamacpp(self, model_id: str, gguf_path: Path, binary: str) -> str:
        existing = self._llamacpp_processes.get(model_id)
        if existing is not None and existing.returncode is None:
            return f"llamacpp-{model_id}"
        port = 8080
        cmd = [
            binary,
            "-m",
            str(gguf_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ctx-size",
            "4096",
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            raise RuntimeLoadError(f"启动 llama-server 失败：{exc}") from exc
        self._llamacpp_processes[model_id] = process

        deadline = time.time() + LLAMACPP_READY_TIMEOUT
        while time.time() < deadline:
            if process.returncode is not None:
                self._llamacpp_processes.pop(model_id, None)
                raise RuntimeLoadError(f"llama-server 进程提前退出（退出码 {process.returncode}）")
            probe = await probe_runtime("llamacpp")
            if probe.get("online"):
                return f"llamacpp-{model_id}"
            await asyncio.sleep(1.0)
        process.terminate()
        self._llamacpp_processes.pop(model_id, None)
        raise RuntimeLoadError(f"llama-server 在 {LLAMACPP_READY_TIMEOUT:.0f}s 内未就绪")

    # ---------- 卸载 ----------

    async def unload(self, model_id: str) -> None:
        process = self._llamacpp_processes.pop(model_id, None)
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10.0)
            except Exception:
                process.kill()
        loaded = self._loaded.pop(model_id, None)
        if loaded and loaded.get("runtime") == "ollama":
            # Ollama 由自身 keep_alive 管理内存，这里只解除应用侧引用
            pass

    def loaded_info(self, model_id: str) -> dict[str, Any] | None:
        return self._loaded.get(model_id)

    async def shutdown(self) -> None:
        for model_id in list(self._llamacpp_processes):
            await self.unload(model_id)


runtime_manager = LocalRuntimeManager()


def models_cache_dir() -> Path:
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    return settings.models_dir
