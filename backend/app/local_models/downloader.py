"""内置小模型下载管理器。

能力（设计文档 10.2）：
- 后端流式管道下载到 backend/models_cache/
- 五态生命周期：NOT_DOWNLOADED / DOWNLOADING / READY / LOADING / ERROR
- 进度、速率、已下/总量、ETA
- 暂停 / 取消 / 重试 / 删除
- 断点续传（HTTP Range + .part 文件）
- SHA-256 完整性校验（下载完成后校验；文档原文写 MD5，此处使用更强的 SHA-256，见交付报告）
- 磁盘占用统计

安全：
- 下载主机白名单（OSVIS_DOWNLOAD_ALLOW_HOSTS），拒绝任意地址拉取（防 SSRF）
- 只允许写入 models_cache 目录，文件名由目录清单固定，不接受用户提供的路径
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..core.config import public_path_label, settings
from ..core.db import upsert_model_record
from .catalog import (
    MODEL_BY_ID,
    STATE_DOWNLOADING,
    STATE_ERROR,
    STATE_LOADING,
    STATE_NOT_DOWNLOADED,
    STATE_READY,
    get_model,
    list_models,
)
from .runtime import RuntimeLoadError

PART_SUFFIX = ".part"


class DownloadError(RuntimeError):
    """下载过程中的可预期错误（网络、校验、白名单）。"""


@dataclass
class DownloadTask:
    model_id: str
    url: str
    target: Path
    part: Path
    expected_bytes: int
    expected_sha256: str

    state: str = STATE_NOT_DOWNLOADED
    bytes_done: int = 0
    bytes_total: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    paused: bool = False
    error: str = ""
    error_code: str = ""
    speed_bps: float = 0.0
    loaded_runtime: str = ""
    runtime_model: str = ""
    _speed_window: list[tuple[float, int]] = field(default_factory=list)
    _pause_requested: bool = False
    _cancel_requested: bool = False
    _runner: asyncio.Task[None] | None = None

    @property
    def percent(self) -> float:
        if self.bytes_total <= 0:
            return 0.0
        return round(min(100.0, self.bytes_done * 100.0 / self.bytes_total), 2)

    @property
    def eta_seconds(self) -> float | None:
        if self.speed_bps <= 0 or self.bytes_total <= self.bytes_done:
            return None
        return round((self.bytes_total - self.bytes_done) / self.speed_bps, 1)

    def to_dict(self, model_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = model_meta or get_model(self.model_id) or {}
        payload: dict[str, Any] = {
            "id": self.model_id,
            "state": self.state,
            "paused": self.paused,
            "bytesDone": self.bytes_done,
            "bytesTotal": self.bytes_total or meta.get("bytesTotal", 0),
            "percent": self.percent,
            "speedBps": round(self.speed_bps, 1),
            "etaSeconds": self.eta_seconds,
            "error": self.error,
            "errorCode": self.error_code,
            "downloaded": self.state == STATE_READY,
            # 载荷文件是否已通过 SHA-256 校验落在 models_cache。
            # 与 downloaded 的区别：装载失败会把状态打回 ERROR，但文件仍在磁盘上，
            # 此时前端应提供“重新装载”而不是让人重新下载数百 MB。
            "fileOnDisk": self.target.is_file(),
            "bytesOnDisk": self.target.stat().st_size if self.target.is_file() else 0,
            "loadedRuntime": self.loaded_runtime,
            "runtimeModel": self.runtime_model,
            "fileName": meta.get("fileName", ""),
            "docSizeLabel": meta.get("docSizeLabel", ""),
        }
        payload.update(
            {
                "name": meta.get("name", self.model_id),
                "parameters": meta.get("parameters", ""),
                "license": meta.get("license", ""),
                "languages": meta.get("languages", ""),
                "ability": meta.get("ability", ""),
                "expectedSpeed": meta.get("expectedSpeed", ""),
                "backends": meta.get("backends", []),
                "quantization": meta.get("quantization", ""),
                "sourceRepo": meta.get("sourceRepo", ""),
                "sourceUrl": meta.get("sourceUrl", ""),
                "sha256": self.expected_sha256,
            }
        )
        return payload


def _assert_host_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DownloadError(f"仅支持 http/https 下载地址，收到 {parsed.scheme or '空'} 协议")
    host = (parsed.hostname or "").lower()
    allow = {h.lower() for h in settings.download_allow_hosts}
    if host not in allow:
        raise DownloadError(
            f"下载主机 {host} 不在白名单内。可用 OSVIS_DOWNLOAD_ALLOW_HOSTS 追加（当前: {sorted(allow)}）"
        )


class ModelDownloadManager:
    """进程内单例：管理 4 款内置模型的下载与装载状态。"""

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = asyncio.Lock()
        self._runtime_manager = None  # 延迟注入，避免循环导入

    # ---------- 初始化与持久化 ----------

    def ensure_loaded(self) -> None:
        """启动时把磁盘现状与数据库记录对齐。"""
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        for meta in list_models():
            model_id = meta["id"]
            if model_id in self._tasks:
                continue
            target = settings.models_dir / meta["fileName"]
            part = settings.models_dir / f"{meta['fileName']}{PART_SUFFIX}"
            task = DownloadTask(
                model_id=model_id,
                url=meta["downloadUrl"],
                target=target,
                part=part,
                expected_bytes=meta["bytesTotal"],
                expected_sha256=meta["sha256"],
            )
            task.bytes_total = meta["bytesTotal"]
            if target.is_file():
                task.state = STATE_READY
                task.bytes_done = target.stat().st_size
            elif part.is_file():
                task.state = STATE_NOT_DOWNLOADED
                task.bytes_done = part.stat().st_size
            else:
                task.state = STATE_NOT_DOWNLOADED
            self._tasks[model_id] = task

    def attach_runtime_manager(self, runtime_manager: Any) -> None:
        self._runtime_manager = runtime_manager

    # ---------- 查询 ----------

    def get_task(self, model_id: str) -> DownloadTask | None:
        return self._tasks.get(model_id)

    def status(self) -> list[dict[str, Any]]:
        self.ensure_loaded()
        return [self._tasks[meta["id"]].to_dict(meta) for meta in list_models()]

    def status_one(self, model_id: str) -> dict[str, Any] | None:
        self.ensure_loaded()
        task = self._tasks.get(model_id)
        if task is None:
            return None
        return task.to_dict()

    def disk_usage(self) -> dict[str, Any]:
        self.ensure_loaded()
        files: list[dict[str, Any]] = []
        total = 0
        for meta in list_models():
            task = self._tasks[meta["id"]]
            size = 0
            if task.target.is_file():
                size = task.target.stat().st_size
            elif task.part.is_file():
                size = task.part.stat().st_size
            files.append({"id": meta["id"], "name": meta["name"], "fileName": meta["fileName"], "bytes": size})
            total += size
        return {"files": files, "totalBytes": total, "directoryLabel": public_path_label(settings.models_dir)}

    # ---------- 下载 ----------

    async def start(self, model_id: str, source_url: str | None = None) -> dict[str, Any]:
        self.ensure_loaded()
        task = self._tasks.get(model_id)
        if task is None:
            raise DownloadError(f"未知的内置模型: {model_id}")
        if task.state == STATE_DOWNLOADING and task._runner and not task._runner.done():
            return task.to_dict()
        url = source_url or task.url
        _assert_host_allowed(url)
        task.url = url
        task.state = STATE_DOWNLOADING
        task.error = ""
        task.error_code = ""
        task.paused = False
        task._pause_requested = False
        task._cancel_requested = False
        task.started_at = time.time()
        task.finished_at = None
        # 重置进度计数：不能沿用上一轮下载（可能是另一份载荷）留下的 bytes_done
        if task.part.is_file():
            task.bytes_done = task.part.stat().st_size
        else:
            task.bytes_done = 0
        task.bytes_total = task.expected_bytes
        task._runner = asyncio.create_task(self._run(task))
        return task.to_dict()

    async def _run(self, task: DownloadTask) -> None:
        try:
            await self._stream(task)
        except asyncio.CancelledError:  # pragma: no cover - 进程退出时
            task.state = STATE_ERROR
            task.error = "下载任务被取消"
            task.error_code = "CANCELLED"
            raise
        except DownloadError as exc:
            task.state = STATE_ERROR
            task.error = str(exc)
            task.error_code = "DOWNLOAD_ERROR"
        except httpx.HTTPStatusError as exc:
            task.state = STATE_ERROR
            task.error_code = f"HTTP_{exc.response.status_code}"
            task.error = (
                f"下载失败：服务端返回 {exc.response.status_code}。"
                + (" 地址或文件名可能已变更。" if exc.response.status_code == 404 else "")
            )
        except httpx.TimeoutException:
            task.state = STATE_ERROR
            task.error_code = "TIMEOUT"
            task.error = "下载超时：网络不稳定或需要代理，可点击重试以断点续传。"
        except httpx.HTTPError as exc:
            task.state = STATE_ERROR
            task.error_code = "NETWORK_ERROR"
            task.error = f"网络错误：{exc}。已保留断点，可点击重试继续下载。"
        finally:
            task._speed_window.clear()
            task.speed_bps = 0.0
            if task.state == STATE_DOWNLOADING and task._pause_requested:
                task.paused = True
                task.state = STATE_NOT_DOWNLOADED
                task.error = ""
                task.error_code = "PAUSED"
            self._persist(task)

    async def _stream(self, task: DownloadTask) -> None:
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        resume_from = task.part.stat().st_size if task.part.is_file() else 0
        headers = {"Range": f"bytes={resume_from}-"} if resume_from > 0 else {}

        # 续传时需要把已有前缀重新喂给哈希器，保证最终校验覆盖完整文件
        hasher = hashlib.sha256()
        if resume_from > 0:
            with task.part.open("rb") as existing:
                while True:
                    block = existing.read(1024 * 1024)
                    if not block:
                        break
                    hasher.update(block)
            task.bytes_done = resume_from

        timeout = httpx.Timeout(connect=20.0, read=60.0, write=60.0, pool=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", task.url, headers=headers) as response:
                if resume_from > 0 and response.status_code == 200:
                    # 服务端不支持 Range：从头重下
                    resume_from = 0
                    task.bytes_done = 0
                    hasher = hashlib.sha256()
                    mode = "wb"
                elif response.status_code in (200, 206):
                    mode = "ab" if resume_from > 0 else "wb"
                else:
                    response.raise_for_status()
                    mode = "wb"

                declared = response.headers.get("content-length")
                if declared and declared.isdigit():
                    declared_bytes = int(declared)
                    task.bytes_total = declared_bytes + resume_from
                else:
                    task.bytes_total = task.expected_bytes
                if task.bytes_total <= 0:
                    task.bytes_total = task.expected_bytes

                window_start = time.time()
                window_bytes = 0
                with task.part.open(mode) as handle:
                    async for chunk in response.aiter_bytes(chunk_size=settings.download_chunk_size):
                        if task._cancel_requested:
                            raise DownloadError("下载已被用户取消")
                        if task._pause_requested:
                            handle.flush()
                            return
                        handle.write(chunk)
                        hasher.update(chunk)
                        task.bytes_done += len(chunk)
                        window_bytes += len(chunk)
                        now = time.time()
                        elapsed = now - window_start
                        if elapsed >= 0.5:
                            instant = window_bytes / elapsed
                            task.speed_bps = instant if task.speed_bps == 0 else task.speed_bps * 0.6 + instant * 0.4
                            window_start = now
                            window_bytes = 0

        actual_size = task.part.stat().st_size
        if task.expected_bytes and actual_size != task.expected_bytes:
            raise DownloadError(
                f"文件大小校验失败：期望 {task.expected_bytes} 字节，实际 {actual_size} 字节，已保留断点可重试"
            )
        digest = hasher.hexdigest()
        if task.expected_sha256 and digest != task.expected_sha256:
            raise DownloadError(
                f"SHA-256 校验失败：期望 {task.expected_sha256[:16]}…，实际 {digest[:16]}…，文件可能已损坏，请重试"
            )
        if task.target.exists():
            task.target.unlink()
        task.part.rename(task.target)
        task.state = STATE_READY
        task.bytes_done = actual_size
        task.bytes_total = actual_size
        task.finished_at = time.time()
        task.error = ""
        task.error_code = ""

    def _persist(self, task: DownloadTask) -> None:
        try:
            upsert_model_record(
                task.model_id,
                state=task.state,
                file_path=str(task.target if task.state == STATE_READY else task.part),
                bytes_done=task.bytes_done,
                bytes_total=task.bytes_total,
                sha256=task.expected_sha256,
                error=task.error,
            )
        except Exception:  # pragma: no cover - 持久化失败不应影响下载主流程
            pass

    # ---------- 控制 ----------

    async def pause(self, model_id: str) -> dict[str, Any]:
        task = self._tasks.get(model_id)
        if task is None:
            raise DownloadError(f"未知的内置模型: {model_id}")
        if task.state == STATE_DOWNLOADING:
            task._pause_requested = True
            if task._runner:
                try:
                    await asyncio.wait_for(asyncio.shield(task._runner), timeout=10.0)
                except Exception:  # 暂停属于尽力而为，超时或异常都不影响后续续传
                    pass
        return task.to_dict()

    async def cancel(self, model_id: str) -> dict[str, Any]:
        task = self._tasks.get(model_id)
        if task is None:
            raise DownloadError(f"未知的内置模型: {model_id}")
        task._cancel_requested = True
        if task._runner and not task._runner.done():
            try:
                await asyncio.wait_for(asyncio.shield(task._runner), timeout=10.0)
            except Exception:  # 取消同样尽力而为
                pass
        if task.part.is_file():
            task.part.unlink()
        task.bytes_done = 0
        task.state = STATE_NOT_DOWNLOADED
        task.paused = False
        task.error = ""
        task.error_code = ""
        self._persist(task)
        return task.to_dict()

    async def retry(self, model_id: str) -> dict[str, Any]:
        self.ensure_loaded()
        task = self._tasks.get(model_id)
        if task is None:
            raise DownloadError(f"未知的内置模型: {model_id}")
        # 载荷已在磁盘上（上一次失败发生在装载环节）时直接恢复 READY：
        # models_cache 里的正式文件只在 SHA-256 校验通过后才会从 .part 改名过来，
        # 因此无需重新走一遍网络下载。
        if task.target.is_file():
            size = task.target.stat().st_size
            if not task.expected_bytes or size == task.expected_bytes:
                task.state = STATE_READY
                task.bytes_done = size
                task.bytes_total = size
                task.paused = False
                task.error = ""
                task.error_code = ""
                self._persist(task)
                return task.to_dict()
        task.error = ""
        task.error_code = ""
        task.paused = False
        return await self.start(model_id, task.url)

    async def delete(self, model_id: str) -> dict[str, Any]:
        task = self._tasks.get(model_id)
        if task is None:
            raise DownloadError(f"未知的内置模型: {model_id}")
        if task.state == STATE_DOWNLOADING:
            raise DownloadError("下载进行中，请先取消或等待完成后再删除")
        if self._runtime_manager is not None:
            await self._runtime_manager.unload(model_id)
        for path in (task.target, task.part):
            if path.is_file():
                path.unlink()
        task.state = STATE_NOT_DOWNLOADED
        task.bytes_done = 0
        task.paused = False
        task.loaded_runtime = ""
        task.runtime_model = ""
        task.error = ""
        task.error_code = ""
        self._persist(task)
        return task.to_dict()

    # ---------- 装载 ----------

    async def load(self, model_id: str) -> dict[str, Any]:
        task = self._tasks.get(model_id)
        if task is None:
            raise DownloadError(f"未知的内置模型: {model_id}")
        if task.state != STATE_READY:
            raise DownloadError("模型尚未下载完成，无法装载")
        if self._runtime_manager is None:
            raise DownloadError("本地运行时管理器未初始化")
        task.state = STATE_LOADING
        self._persist(task)
        try:
            result = await self._runtime_manager.load(model_id, task.target)
            task.state = STATE_READY
            task.loaded_runtime = result.get("runtime", "")
            task.runtime_model = result.get("runtimeModel", "")
            task.error = ""
            task.error_code = ""
        except DownloadError as exc:
            task.state = STATE_ERROR
            task.error = str(exc)
            task.error_code = "LOAD_FAILED"
        except RuntimeLoadError as exc:
            # 装载失败也必须落地成 ERROR/LOAD_FAILED，不能把状态卡在 LOADING
            task.state = STATE_ERROR
            task.error = str(exc)
            task.error_code = "LOAD_FAILED"
        finally:
            self._persist(task)
        return task.to_dict()

    async def unload(self, model_id: str) -> dict[str, Any]:
        task = self._tasks.get(model_id)
        if task is None:
            raise DownloadError(f"未知的内置模型: {model_id}")
        if self._runtime_manager is not None:
            await self._runtime_manager.unload(model_id)
        task.loaded_runtime = ""
        task.runtime_model = ""
        if task.state == STATE_ERROR:
            task.state = STATE_READY if task.target.is_file() else STATE_NOT_DOWNLOADED
            task.error = ""
            task.error_code = ""
        self._persist(task)
        return task.to_dict()


manager = ModelDownloadManager()
manager.ensure_loaded()
