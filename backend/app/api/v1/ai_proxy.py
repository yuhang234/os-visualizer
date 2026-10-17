"""统一大模型 SSE 流式代理 + 厂商配置管理。

设计文档：
- 第 8.1 节：前端 → 后端统一代理 → 公有云厂商 / 中转网关 / 本地离线
- 第 13.2 节 5/6：`POST /api/v1/ai/chat/stream`、模型引擎接口
- 第 10.3 节：API Key 零明文入库，前端只拿掩码；落库前 Fernet 加密

SSE 帧协议（本模块与前端 `src/services/chatApi.ts` 的既定契约）：
    data: {"type":"meta","provider":...,"model":...,"source":...,"quota":{...}}
    data: {"type":"delta","content":"..."}        # 逐块增量文本
    data: {"type":"error","code":"...","message":"..."}
    data: {"type":"done"}                          # 正常收尾
    data: [DONE]                                   # 流终止标志（设计文档原文要求）
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ...core import db
from ...core.config import settings
from ...core.crypto import decrypt_secret, encrypt_secret, mask_secret
from ...providers.catalog import get_provider_template, list_provider_templates
from ...providers.client import UpstreamError, stream_provider
from ...providers.local_runtimes import list_local_runtimes
from ...schemas.common import ok
from ...schemas.engine import ChatStreamRequest, ProviderConfigIn
from ..deps import client_key, current_user_optional

router = APIRouter(prefix="/ai", tags=["ai"])

# 内置离线演示后端：无任何外部依赖，用于无密钥 / 断网环境端到端验证 SSE 链路。
# 设计文档第 9.1 节的 12 家厂商模板保持原样，mock 作为系统级兜底引擎单独暴露，
# 该决定记录在交付报告中。
BUILTIN_MOCK_KEY = "builtin-mock"
MOCK_PROVIDER: dict[str, Any] = {
    "key": BUILTIN_MOCK_KEY,
    "name": "内置演示后端（离线 mock）",
    "baseUrl": "",
    "defaultModel": "osvis-mock-tutor",
    "models": ["osvis-mock-tutor"],
    "authHeader": "Authorization",
    "authScheme": "Bearer",
    "extraHeaders": {},
    "openAiCompatible": True,
    "sseTextPath": "choices.0.delta.content",
    "nativeProtocol": "mock",
    "category": "builtin",
    "docsUrl": "",
    "requiresApiKey": False,
}

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 关闭 Nginx 缓冲，保证逐块到达浏览器
}


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


# ---------------- 厂商配置管理 ----------------


def _config_out(row: Any) -> dict[str, Any]:
    """数据库行 → 前端可见结构（只含掩码，绝不含明文密钥）。"""
    cipher = row["api_key_cipher"] or ""
    masked = ""
    if cipher:
        try:
            masked = mask_secret(decrypt_secret(cipher))
        except ValueError:
            masked = "（密文不可解密，请重新填写）"
    try:
        extra_headers = json.loads(row["extra_headers"] or "{}")
    except json.JSONDecodeError:
        extra_headers = {}
    template = get_provider_template(row["provider_key"])
    return {
        "id": int(row["id"]),
        "providerKey": row["provider_key"],
        "displayName": row["display_name"],
        "baseUrl": row["base_url"],
        "model": row["model"],
        "apiKeyMasked": masked,
        "hasApiKey": bool(cipher),
        "extraHeaders": extra_headers,
        "isLocal": bool(row["is_local"]),
        "isActive": bool(row["is_active"]),
        "openAiCompatible": bool(template.get("openAiCompatible", True)) if template else True,
        "providerName": template.get("name") if template else row["display_name"],
        "updatedAt": row["updated_at"],
    }


def _target_from_row(row: Any, payload: ChatStreamRequest) -> dict[str, Any]:
    provider = dict(get_provider_template(row["provider_key"]) or {})
    provider.setdefault("key", row["provider_key"])
    try:
        extra = json.loads(row["extra_headers"] or "{}")
    except json.JSONDecodeError:
        extra = {}
    merged_extra = dict(provider.get("extraHeaders") or {})
    merged_extra.update(extra)
    provider["extraHeaders"] = merged_extra
    provider["baseUrl"] = row["base_url"]
    try:
        api_key = decrypt_secret(row["api_key_cipher"] or "")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"密钥解密失败：{exc}") from exc
    return {
        "provider": provider,
        "model": payload.model or row["model"],
        "apiKey": api_key,
        "source": "user-config",
        "configId": int(row["id"]),
    }


@router.get("/engine/providers")
def list_providers(user: dict[str, Any] | None = Depends(current_user_optional)) -> dict[str, Any]:
    """列出当前身份（登录用户 / 游客）名下的模型接入配置。"""
    user_id = user["id"] if user else None
    rows = db.list_provider_configs(user_id)
    return ok([_config_out(row) for row in rows])


@router.put("/engine/providers")
def save_provider(payload: ProviderConfigIn, user: dict[str, Any] | None = Depends(current_user_optional)) -> dict[str, Any]:
    """新增或更新一个厂商 / 中转配置。apiKey 留空表示保留原密钥，传空串表示清除。"""
    user_id = user["id"] if user else None
    template = get_provider_template(payload.providerKey)
    if template is None:
        raise HTTPException(status_code=400, detail=f"未知的厂商模板: {payload.providerKey}")

    existing = db.get_provider_config_by_key(payload.providerKey, user_id)
    encrypted = existing["api_key_cipher"] if existing is not None else ""
    if payload.apiKey is None:
        pass
    elif payload.apiKey == "":
        encrypted = ""
    else:
        encrypted = encrypt_secret(payload.apiKey.strip())

    merged_headers = dict(template.get("extraHeaders") or {})
    merged_headers.update({str(k): str(v) for k, v in payload.extraHeaders.items()})
    if template.get("authHeader") and template["authHeader"] != "Authorization":
        # 厂商自定义鉴权头（如 Anthropic 的 x-api-key）由模板负责，不进入用户额外头
        merged_headers.pop(template["authHeader"], None)
    merged_headers.pop("Authorization", None)

    result = db.upsert_provider_config(
        user_id=user_id,
        provider_key=payload.providerKey,
        display_name=payload.displayName or template["name"],
        base_url=payload.baseUrl.strip(),
        model=payload.model.strip() or template.get("defaultModel", ""),
        api_key_cipher=encrypted,
        extra_headers=json.dumps(merged_headers, ensure_ascii=False),
        is_local=payload.isLocal,
    )
    row = db.get_provider_config(int(result["id"]), user_id)
    return ok(_config_out(row), message="配置已保存（密钥仅存于后端，前端只显示掩码）")


@router.post("/engine/providers/{provider_id}/activate")
def activate_provider(provider_id: int, user: dict[str, Any] | None = Depends(current_user_optional)) -> dict[str, Any]:
    user_id = user["id"] if user else None
    row = db.get_provider_config(provider_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置不存在或无权访问")
    db.set_active_provider(provider_id, user_id)
    refreshed = db.get_provider_config(provider_id, user_id)
    return ok(_config_out(refreshed), message="已切换为当前对话引擎")


@router.delete("/engine/providers/{provider_id}")
def delete_provider(provider_id: int, user: dict[str, Any] | None = Depends(current_user_optional)) -> dict[str, Any]:
    user_id = user["id"] if user else None
    if not db.delete_provider_config(provider_id, user_id):
        raise HTTPException(status_code=404, detail="配置不存在或无权删除")
    return ok({"deleted": True}, message="配置已删除")


# ---------------- 上下文快照注入 ----------------


def _format_vector(values: Any) -> str:
    if isinstance(values, list):
        return "(" + ", ".join(str(v) for v in values) + ")"
    return str(values)


def build_system_prompt(snapshot: dict[str, Any]) -> str:
    """把前端勾选的算法快照渲染成系统提示词（设计文档 8.2：算法快照附带）。"""
    lines = [
        "你是「OS Visualizer 操作系统核心原理可视化教学平台」的 AI 教学助教。",
        "回答要求：先给结论，再给推导过程；使用 Markdown；数学公式用 $...$ 或 $$...$$；",
        "涉及算法步骤时结合下面提供的当前实验快照数据来解释，不要编造快照中不存在的数值。",
    ]
    page_rep = snapshot.get("pageReplacement") or snapshot.get("pageReplacementSnapshot")
    banker = snapshot.get("banker") or snapshot.get("bankerSnapshot")
    threads = snapshot.get("threads") or snapshot.get("threadsSnapshot")
    blocks: list[str] = []
    if isinstance(page_rep, dict):
        parts = [
            f"算法：{page_rep.get('algorithm', '未知')}",
            f"页框数：{page_rep.get('frameCount', '未知')}",
        ]
        if isinstance(page_rep.get("frames"), list):
            parts.append("当前页框内容：" + _format_vector(page_rep["frames"]))
        if page_rep.get("hits") is not None or page_rep.get("misses") is not None:
            parts.append(f"命中 {page_rep.get('hits')} 次 / 缺页 {page_rep.get('misses')} 次")
        if page_rep.get("missRate") is not None:
            parts.append(f"缺页率 {float(page_rep['missRate']) * 100:.1f}%")
        if isinstance(page_rep.get("referenceString"), list):
            parts.append("参考串：" + ",".join(str(v) for v in page_rep["referenceString"][:60]))
        blocks.append("【页面置换当前快照】\n" + "\n".join(f"- {p}" for p in parts))
    if isinstance(banker, dict):
        parts = []
        if banker.get("available") is not None:
            parts.append("Available = " + _format_vector(banker["available"]))
        for key, label in (("maxMatrix", "Max"), ("allocationMatrix", "Allocation"), ("needMatrix", "Need")):
            matrix = banker.get(key)
            if isinstance(matrix, list):
                for index, row in enumerate(matrix):
                    parts.append(f"{label}[P{index}] = {_format_vector(row)}")
        if banker.get("isSafe") is not None:
            parts.append(f"安全性判定：{'安全' if banker['isSafe'] else '不安全'}")
        if isinstance(banker.get("safeSequence"), list) and banker["safeSequence"]:
            parts.append("安全序列 = " + " → ".join(str(p) for p in banker["safeSequence"]))
        blocks.append("【银行家算法当前快照】\n" + "\n".join(f"- {p}" for p in parts))
    if isinstance(threads, dict):
        parts = []
        for key, label in (
            ("bufferCapacity", "缓冲区容量"),
            ("bufferCount", "当前产品数"),
            ("produced", "累计生产"),
            ("consumed", "累计消费"),
        ):
            if threads.get(key) is not None:
                parts.append(f"{label}：{threads[key]}")
        semaphores = threads.get("semaphores") or {}
        if semaphores:
            parts.append(
                f"信号量 mutex={semaphores.get('mutex')}、empty={semaphores.get('empty')}、full={semaphores.get('full')}"
            )
        if isinstance(threads.get("bufferState"), list):
            parts.append("缓冲区：" + _format_vector(threads["bufferState"]))
        blocks.append("【生产者-消费者当前快照】\n" + "\n".join(f"- {p}" for p in parts))
    if blocks:
        lines.append("")
        lines.append("以下是学生当前界面上的实验数据快照：")
        lines.extend(blocks)
    return "\n".join(lines)


# ---------------- 对话目标解析 ----------------


def _resolve_target(
    payload: ChatStreamRequest,
    user: dict[str, Any] | None,
) -> dict[str, Any]:
    """决定这次对话真正请求哪个上游。

    优先级：显式 providerId → 显式 providerKey（有保存配置用之，否则模板 + 服务端密钥）→
    当前激活配置 → 服务端默认云端 Key → 内置 mock 兜底。
    显式指定的目标必须先于"自动激活配置"解析，否则用户点名要用的引擎会被悄悄换掉。
    """
    user_id = user["id"] if user else None
    if payload.providerId is not None:
        row = db.get_provider_config(payload.providerId, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="指定的引擎配置不存在或无权访问")
        return _target_from_row(row, payload)

    if payload.providerKey:
        if payload.providerKey == BUILTIN_MOCK_KEY:
            return {"provider": dict(MOCK_PROVIDER), "model": payload.model or MOCK_PROVIDER["defaultModel"], "apiKey": "", "source": "builtin-mock", "configId": None}
        template = get_provider_template(payload.providerKey)
        if template is None:
            raise HTTPException(status_code=400, detail=f"未知的厂商模板: {payload.providerKey}")
        saved = db.get_provider_config_by_key(payload.providerKey, user_id)
        if saved is not None:
            return _target_from_row(saved, payload)
        provider = dict(template)
        if settings.server_api_key:
            if settings.server_base_url:
                provider["baseUrl"] = settings.server_base_url
            return {
                "provider": provider,
                "model": payload.model or template.get("defaultModel", ""),
                "apiKey": settings.server_api_key,
                "source": "server-default",
                "configId": None,
            }
        return {
            "provider": provider,
            "model": payload.model or template.get("defaultModel", ""),
            "apiKey": "",
            "source": "template-no-key",
            "configId": None,
        }

    active = db.get_active_provider(user_id)
    if active is not None:
        return _target_from_row(active, payload)

    if settings.server_api_key:
        template = dict(get_provider_template(settings.default_provider) or {})
        template.setdefault("key", settings.default_provider)
        template["baseUrl"] = settings.server_base_url or template.get("baseUrl", "")
        return {
            "provider": template,
            "model": payload.model or settings.default_model,
            "apiKey": settings.server_api_key,
            "source": "server-default",
            "configId": None,
        }

    # 无任何可用云端配置：回退到内置离线演示后端，保证功能链路端到端可用
    return {
        "provider": dict(MOCK_PROVIDER),
        "model": payload.model or MOCK_PROVIDER["defaultModel"],
        "apiKey": "",
        "source": "builtin-mock",
        "configId": None,
    }


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    user: dict[str, Any] | None = Depends(current_user_optional),
    guest_id: str = Depends(client_key),
) -> StreamingResponse:
    target = _resolve_target(payload, user)
    provider: dict[str, Any] = target["provider"]
    model: str = target["model"]
    api_key: str = target["apiKey"]
    source: str = target["source"]

    uses_server_key = source == "server-default" and user is None
    if uses_server_key:
        used = db.get_usage(guest_id)
        if used >= settings.guest_daily_chat_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"游客每日免费对话额度已用尽（{settings.guest_daily_chat_limit} 次）。"
                    "请登录账号，或在「模型引擎设置」中配置自己的厂商密钥 / 连接本地 Ollama 后不限次数。"
                ),
            )

    messages = [{"role": m.role, "content": m.content} for m in payload.messages]
    snapshot = payload.contextSnapshot
    if snapshot:
        system_prompt = build_system_prompt(snapshot)
        if messages and messages[0]["role"] == "system":
            messages[0] = {"role": "system", "content": messages[0]["content"] + "\n\n" + system_prompt}
        else:
            messages.insert(0, {"role": "system", "content": system_prompt})

    async def event_stream() -> AsyncIterator[str]:
        yield _sse(
            {
                "type": "meta",
                "provider": provider.get("key"),
                "providerName": provider.get("name"),
                "model": model,
                "source": source,
                "conversationId": payload.conversationId,
            }
        )
        try:
            async for chunk in stream_provider(provider, model, messages, api_key, context_snapshot=snapshot):
                if chunk:
                    yield _sse({"type": "delta", "content": chunk})
            if uses_server_key:
                db.increment_usage(guest_id)
        except UpstreamError as exc:
            yield _sse({"type": "error", "code": exc.code, "message": str(exc)})
        except Exception as exc:  # pragma: no cover - 兜底，避免连接静默中断
            yield _sse({"type": "error", "code": "INTERNAL_ERROR", "message": f"代理转发失败：{exc}"})
        # 无论成功失败都发 done + [DONE] 正常收尾，前端据此结束流（设计文档 SSE 终止约定）
        yield _sse({"type": "done"})
        yield _sse_done()

    return StreamingResponse(event_stream(), media_type="text/event-stream; charset=utf-8", headers=dict(SSE_HEADERS))


@router.get("/engine/catalog")
def engine_catalog(user: dict[str, Any] | None = Depends(current_user_optional)) -> dict[str, Any]:
    """引擎设置页一次性拉取的静态元数据：12 厂商模板 + 本地部署方案 + 内置 mock。"""
    user_id = user["id"] if user else None
    return ok(
        {
            "providers": list_provider_templates(),
            "localRuntimes": list_local_runtimes(),
            "mock": MOCK_PROVIDER,
            "saved": [_config_out(row) for row in db.list_provider_configs(user_id)],
            "guest": {
                "dailyChatLimit": settings.guest_daily_chat_limit,
                "isGuest": user is None,
            },
            "serverDefaults": {
                "provider": settings.default_provider,
                "model": settings.default_model,
                "hasServerKey": bool(settings.server_api_key),
            },
        }
    )
