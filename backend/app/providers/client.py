"""大模型统一代理适配器。

设计文档第 8.1 节架构拓扑：前端 → 后端统一代理 → 公有云厂商 / 中转网关 / 本地离线。

适配协议：
1. `openai`（含 11 家 OpenAI 兼容厂商、自定义中转、Ollama / LM Studio / llama.cpp / vLLM）
   POST {base_url}/chat/completions，SSE 增量位于 choices[0].delta.content
2. `anthropic-messages`（Anthropic Claude 原生 Messages 格式）
   POST {base_url}/messages，SSE 增量位于 content_block_delta.delta.text
3. `mock`（内置离线演示后端）
   无外部依赖，逐字推送教学回答，用于无密钥/断网环境端到端验证
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

# 上游读取超时：大模型首 token 可能较慢，给足 120s
UPSTREAM_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=15.0)

# 内置 mock 后端的逐块推送间隔：可用 OSVIS_MOCK_CHUNK_DELAY 调低，便于自动化测试快速跑完
MOCK_CHUNK_DELAY = float(os.environ.get("OSVIS_MOCK_CHUNK_DELAY", "") or 0.018)


class UpstreamError(RuntimeError):
    """上游厂商返回可展示的错误。"""

    def __init__(self, message: str, *, code: str = "UPSTREAM_ERROR", status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def classify_http_error(status: int, body: str) -> UpstreamError:
    """把上游 HTTP 错误码翻译成清晰的中文诊断。"""
    snippet = (body or "").strip().replace("\n", " ")[:300]
    if status in (401, 403):
        return UpstreamError(f"密钥无效或无权限（HTTP {status}）：{snippet}", code="AUTH_FAILED", status=status)
    if status == 404:
        return UpstreamError(
            f"模型或路径不存在（HTTP 404）：{snippet}。请检查 base_url 是否包含 /v1，以及模型名是否正确。",
            code="MODEL_NOT_FOUND",
            status=status,
        )
    if status == 429:
        return UpstreamError(f"触发上游限流（HTTP 429）：{snippet}", code="RATE_LIMITED", status=status)
    if status >= 500:
        return UpstreamError(f"上游服务异常（HTTP {status}）：{snippet}", code="UPSTREAM_5XX", status=status)
    return UpstreamError(f"上游返回错误（HTTP {status}）：{snippet}", code=f"HTTP_{status}", status=status)


def build_headers(provider: dict[str, Any], api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    auth_header = provider.get("authHeader", "Authorization")
    auth_scheme = provider.get("authScheme", "Bearer")
    if api_key:
        headers[auth_header] = f"{auth_scheme} {api_key}".strip() if auth_scheme else api_key
    for key, value in (provider.get("extraHeaders") or {}).items():
        headers[str(key)] = str(value)
    return headers


def build_request_payload(provider: dict[str, Any], model: str, messages: list[dict[str, str]], stream: bool) -> dict[str, Any]:
    if provider.get("nativeProtocol") == "anthropic-messages":
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        chat_messages = [m for m in messages if m.get("role") != "system"]
        payload: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": 2048,
            "stream": stream,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return payload
    return {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": 0.6,
    }


def _endpoint(provider: dict[str, Any]) -> str:
    base = (provider.get("baseUrl") or "").rstrip("/")
    if provider.get("nativeProtocol") == "anthropic-messages":
        return f"{base}/messages"
    return f"{base}/chat/completions"


def extract_delta(provider: dict[str, Any], payload: Any) -> str:
    """按厂商模板声明的 sseTextPath 提取增量文本。"""
    path = provider.get("sseTextPath", "choices.0.delta.content")
    current = payload
    for part in str(path).split("."):
        if isinstance(current, list):
            if not part.isdigit() or int(part) >= len(current):
                return ""
            current = current[int(part)]
        elif isinstance(current, dict):
            if part not in current:
                return ""
            current = current[part]
        else:
            return ""
    return current if isinstance(current, str) else ""


async def stream_openai_compatible(
    provider: dict[str, Any],
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
) -> AsyncIterator[str]:
    url = _endpoint(provider)
    headers = build_headers(provider, api_key)
    payload = build_request_payload(provider, model, messages, stream=True)
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise classify_http_error(response.status_code, body)
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and parsed.get("error"):
                    message = parsed["error"]
                    if isinstance(message, dict):
                        message = message.get("message", json.dumps(message, ensure_ascii=False))
                    raise UpstreamError(f"上游返回错误：{message}", code="UPSTREAM_BODY_ERROR")
                delta = extract_delta(provider, parsed)
                if delta:
                    yield delta


async def stream_anthropic(
    provider: dict[str, Any],
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
) -> AsyncIterator[str]:
    url = _endpoint(provider)
    headers = build_headers(provider, api_key)
    payload = build_request_payload(provider, model, messages, stream=True)
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise classify_http_error(response.status_code, body)
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and parsed.get("type") == "error":
                    detail = parsed.get("error", {})
                    raise UpstreamError(
                        f"上游返回错误：{detail.get('message', json.dumps(detail, ensure_ascii=False))}",
                        code="UPSTREAM_BODY_ERROR",
                    )
                delta = extract_delta(provider, parsed)
                if delta:
                    yield delta


# ---------------- 内置 mock 后端 ----------------


def _format_vector(values: Any) -> str:
    if isinstance(values, list):
        return "(" + ", ".join(str(v) for v in values) + ")"
    return str(values)


def build_mock_answer(user_text: str, context_snapshot: dict[str, Any] | None) -> str:
    """依据上下文快照生成一段有教学价值的结构化回答。

    这是离线演示后端：不访问任何外部网络，输出内容基于用户提问与前端注入的算法快照拼装，
    目的是让"无厂商密钥 / 断网"环境也能完整验证 SSE 流式链路与 Markdown 渲染。
    """
    snapshot = context_snapshot or {}
    lines: list[str] = []
    lines.append("### 本地演示助教（内置离线后端）")
    lines.append("")
    lines.append(
        "当前对话由 **内置 mock 后端** 应答：它不访问任何外部网络，用于在没有厂商密钥或断网时"
        "验证流式链路、Markdown 与公式渲染。配置任意厂商密钥或连接本地 Ollama 后即可获得真实模型回答。"
    )
    lines.append("")

    page_rep = snapshot.get("pageReplacement") or snapshot.get("pageReplacementSnapshot")
    banker = snapshot.get("banker") or snapshot.get("bankerSnapshot")
    threads = snapshot.get("threads") or snapshot.get("threadsSnapshot")

    if page_rep:
        algorithm = page_rep.get("algorithm", "未知")
        misses = page_rep.get("misses")
        hits = page_rep.get("hits")
        miss_rate = page_rep.get("missRate")
        frames = page_rep.get("frames")
        lines.append(f"#### 页面置换快照分析（{algorithm}）")
        lines.append("")
        if isinstance(misses, int) and isinstance(hits, int):
            total = hits + misses
            rate = (misses / total * 100) if total else 0.0
            lines.append(f"- 已访问 {total} 次，命中 {hits} 次，缺页 {misses} 次，缺页率约 {rate:.1f}%")
        if isinstance(frames, list):
            resident = [str(f) for f in frames if f is not None]
            lines.append(f"- 当前驻留页面：{'、'.join(resident) if resident else '（页框全空）'}")
        if algorithm == "FIFO":
            lines.append(
                "- FIFO 只看页面进入内存的先后顺序，命中不会改变淘汰顺序，因此可能出现 Belady 异常"
                "（页框变多反而缺页更多）。"
            )
        elif algorithm == "LRU":
            lines.append("- LRU 依据「最近最久未使用」淘汰，命中会刷新页面的新鲜度，能较好利用程序局部性。")
        elif algorithm == "OPT":
            lines.append("- OPT 需要预知未来访问串，是理论下界，只用于对比教学，无法在实际系统中实现。")
        elif algorithm == "CLOCK":
            lines.append("- CLOCK 用访问位近似 LRU：命中置 1，缺页时指针扫描，遇到 1 就清零并给第二次机会。")
        lines.append("")

    if banker:
        lines.append("#### 银行家算法快照分析")
        lines.append("")
        if "available" in banker:
            lines.append(f"- 当前 Available = {_format_vector(banker.get('available'))}")
        if banker.get("needMatrix"):
            need_rows = banker["needMatrix"]
            if isinstance(need_rows, list):
                for index, row in enumerate(need_rows):
                    lines.append(f"- Need[P{index}] = {_format_vector(row)}")
        lines.append(
            "- 安全状态 ≠ 不会死锁的充分条件：安全性检查只保证存在一条让所有进程依次完成的顺序，"
            "因此每次实际分配前都要先做一次试探性分配 + 安全性检查。"
        )
        lines.append("")

    if threads:
        lines.append("#### 生产者-消费者快照分析")
        lines.append("")
        if "bufferCapacity" in threads:
            lines.append(f"- 缓冲区容量 {threads['bufferCapacity']}，当前产品数 {threads.get('bufferCount', '未知')}")
        semaphores = threads.get("semaphores") or {}
        if semaphores:
            lines.append(
                f"- 信号量：mutex={semaphores.get('mutex')}，empty={semaphores.get('empty')}，full={semaphores.get('full')}"
            )
            lines.append("- 恒有 `empty + full = 缓冲区容量`，这是判断模拟是否自洽的重要不变量。")
        lines.append(
            "- 若把生产者的两个 P 操作顺序颠倒（先 P(mutex) 再 P(empty)），缓冲区满时就会持锁等待，"
            "消费者无法取走产品，形成死锁。"
        )
        lines.append("")

    if not (page_rep or banker or threads):
        lines.append("#### 通用操作系统原理速览")
        lines.append("")
        lines.append(
            "1. **页面置换**：内存不足时决定淘汰哪一页。FIFO 简单但可能 Belady 异常；LRU 利用局部性；"
            "OPT 是理论最优；CLOCK 用访问位近似 LRU，开销低。"
        )
        lines.append(
            "2. **死锁避免（银行家算法）**：把系统状态划分为安全与不安全，分配前先做试探分配并检查是否仍存在安全序列。"
        )
        lines.append(
            "3. **同步互斥**：互斥锁保护临界区，信号量表达「资源计数」。有界缓冲区的经典解需要"
            "互斥锁 + 空位信号量 + 产品信号量三者配合。"
        )
        lines.append("")

    if user_text.strip():
        lines.append("#### 关于你的提问")
        lines.append("")
        preview = user_text.strip().replace("\n", " ")[:200]
        lines.append(f"> {preview}")
        lines.append("")
        lines.append(
            "建议在左侧三个算法页面调整参数并逐步回放，观察状态快照的演化；把当前快照勾选「附带算法快照」"
            "后提问，回答会结合你眼前的具体数据。"
        )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "想接入真实模型？打开 **模型引擎设置** → 选择任一厂商模板填入 API Key，"
        "或点击 **探测本地 Ollama** 一键接入本机模型。密钥只保存在后端 SQLite（加密存储），"
        "前端始终只看到掩码。"
    )
    return "\n".join(lines)


async def stream_mock(
    messages: list[dict[str, str]],
    context_snapshot: dict[str, Any] | None,
) -> AsyncIterator[str]:
    user_text = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            user_text = message.get("content", "")
            break
    answer = build_mock_answer(user_text, context_snapshot)
    # 按小块推送，模拟打字机；标点与换行处稍作停顿，观感更自然
    buffer = ""
    for char in answer:
        buffer += char
        if len(buffer) >= 3 or char in "\n。！？；":
            yield buffer
            buffer = ""
            await asyncio.sleep(MOCK_CHUNK_DELAY)
    if buffer:
        yield buffer


STREAMERS = {
    "openai": stream_openai_compatible,
    "anthropic-messages": stream_anthropic,
}


async def stream_provider(
    provider: dict[str, Any],
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
    context_snapshot: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    protocol = provider.get("nativeProtocol") or ("anthropic-messages" if provider.get("key") == "anthropic" else "openai")
    if protocol == "mock":
        async for chunk in stream_mock(messages, context_snapshot):
            yield chunk
        return
    streamer = STREAMERS.get(protocol)
    if streamer is None:
        raise UpstreamError(f"暂不支持的协议类型: {protocol}", code="UNSUPPORTED_PROTOCOL")
    async for chunk in streamer(provider, model, messages, api_key):
        yield chunk


# ---------------- 连通性探测 ----------------


async def ping_provider(provider: dict[str, Any], api_key: str, model: str) -> dict[str, Any]:
    """测试连接：优先 GET /models，失败则退化为一次最小 chat 请求。"""
    base = (provider.get("baseUrl") or "").rstrip("/")
    if not base:
        return {"ok": False, "errorCode": "NO_BASE_URL", "error": "请先填写 base_url"}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=8.0, read=20.0, write=20.0, pool=8.0)) as client:
            headers = build_headers(provider, api_key)
            headers.pop("Accept", None)
            response = await client.get(f"{base}/models", headers=headers)
            if response.status_code == 200:
                latency = round((time.perf_counter() - started) * 1000, 1)
                models: list[str] = []
                try:
                    payload = response.json()
                    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                        for entry in payload["data"]:
                            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                                models.append(entry["id"])
                except ValueError:
                    pass
                return {
                    "ok": True,
                    "latencyMs": latency,
                    "httpStatus": 200,
                    "probePath": "/models",
                    "models": models[:50],
                    "modelExists": (model in models) if (model and models) else None,
                    "errorCode": None,
                    "error": None,
                }
            if response.status_code in (401, 403, 404, 405, 400):
                # 不少网关不实现 /models，退化为最小 chat 请求
                fallback = await _ping_with_chat(provider, api_key, model)
                if fallback.get("ok"):
                    return fallback
                error = classify_http_error(response.status_code, response.text[:200])
                return {
                    "ok": False,
                    "httpStatus": response.status_code,
                    "probePath": "/models",
                    "latencyMs": round((time.perf_counter() - started) * 1000, 1),
                    "errorCode": error.code,
                    "error": f"{error}（同时最小对话探测也失败：{fallback.get('error')}）",
                }
            error = classify_http_error(response.status_code, response.text[:200])
            return {
                "ok": False,
                "httpStatus": response.status_code,
                "probePath": "/models",
                "latencyMs": round((time.perf_counter() - started) * 1000, 1),
                "errorCode": error.code,
                "error": str(error),
            }
    except httpx.TimeoutException:
        return {
            "ok": False,
            "errorCode": "TIMEOUT",
            "error": "连接超时：网络不可达、需要代理，或本地服务未启动",
            "latencyMs": round((time.perf_counter() - started) * 1000, 1),
        }
    except httpx.ConnectError as exc:
        return {
            "ok": False,
            "errorCode": "CONNECT_ERROR",
            "error": f"无法建立连接：{exc}",
            "latencyMs": round((time.perf_counter() - started) * 1000, 1),
        }
    except httpx.HTTPError as exc:  # pragma: no cover
        return {"ok": False, "errorCode": "NETWORK_ERROR", "error": str(exc)}


async def _ping_with_chat(provider: dict[str, Any], api_key: str, model: str) -> dict[str, Any]:
    if not model:
        return {"ok": False, "error": "未填写模型名，且该网关未提供 /models 列表"}
    started = time.perf_counter()
    payload = build_request_payload(provider, model, [{"role": "user", "content": "ping"}], stream=False)
    payload["max_tokens"] = 1
    url = _endpoint(provider)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=8.0, read=30.0, write=20.0, pool=8.0)) as client:
            response = await client.post(url, json=payload, headers=build_headers(provider, api_key))
        latency = round((time.perf_counter() - started) * 1000, 1)
        if response.status_code < 400:
            return {
                "ok": True,
                "latencyMs": latency,
                "httpStatus": response.status_code,
                "probePath": "/chat/completions (minimal)",
                "models": [],
                "modelExists": True,
                "errorCode": None,
                "error": None,
            }
        error = classify_http_error(response.status_code, response.text[:200])
        return {"ok": False, "httpStatus": response.status_code, "errorCode": error.code, "error": str(error)}
    except httpx.TimeoutException:
        return {"ok": False, "errorCode": "TIMEOUT", "error": "最小对话探测超时"}
    except httpx.HTTPError as exc:
        return {"ok": False, "errorCode": "NETWORK_ERROR", "error": str(exc)}


CONTEXT_SNAPSHOT_HINT = re.compile(r"\s+")
