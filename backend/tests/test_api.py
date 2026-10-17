"""HTTP 接口契约测试：鉴权、四大算法接口、SSE 对话链路、厂商配置掩码、引擎探测、模型下载五态。

网络原则：全部用例离线可跑。需要"真实上游"的场景由本文件内置的本地 HTTP 服务器扮演
（OpenAI 兼容 /models 与 /chat/completions、支持 Range 的 GGUF 静态文件）。
"""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator
from urllib.parse import urlparse

import pytest

from app.core import db as db_module
from app.core.config import settings

FIFO_REFERENCE = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
CHAT_URL = "/api/v1/ai/chat/stream"


# ---------------- 本地假上游 ----------------


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    """扮演 OpenAI 兼容网关 + 静态模型文件服务器。"""

    protocol_version = "HTTP/1.1"
    chatbot_payload: bytes = b""
    model_bytes: bytes = b""
    slow_stream: bool = False
    range_requests: list[str] = []
    download_requests: int = 0
    auth_headers: list[str] = []

    def log_message(self, *args: Any) -> None:  # 静音
        pass

    def _send(self, code: int, body: bytes, content_type: str = "application/json", extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/v1/broken"):
            self._send(500, b'{"error":{"message":"boom"}}')
            return
        if path == "/api/tags":  # Ollama 原生探测路径
            self._send(200, json.dumps({"models": [{"name": "local-test-model", "size": 123}]}).encode())
            return
        if path == "/v1/models":
            type(self).auth_headers.append(self.headers.get("Authorization") or "")
            self._send(200, json.dumps({"object": "list", "data": [{"id": "local-test-model"}]}).encode())
            return
        if path == "/v1/model.gguf":
            payload = type(self).model_bytes
            type(self).download_requests += 1
            range_header = self.headers.get("Range")
            if range_header:
                type(self).range_requests.append(range_header)
                start = int(range_header.split("=")[1].split("-")[0])
                body = payload[start:]
                self.send_response(206)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Range", f"bytes {start}-{len(payload) - 1}/{len(payload)}")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if type(self).slow_stream:
                for offset in range(0, len(payload), 8 * 1024):
                    self.wfile.write(payload[offset : offset + 8 * 1024])
                    self.wfile.flush()
                    time.sleep(0.05)
            else:
                self.wfile.write(payload)
            return
        if path == "/v1/broken":
            self._send(500, b'{"error":{"message":"boom"}}')
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        type(self).auth_headers.append(self.headers.get("Authorization") or "")
        if path == "/v1/broken/chat/completions":
            self._send(500, b'{"error":{"message":"boom"}}')
            return
        if path == "/v1/chat/completions":
            body = type(self).chatbot_payload
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send(404, b'{"error":"not found"}')


@pytest.fixture(scope="module")
def upstream() -> Iterator[dict[str, Any]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield {"base": base, "server": server, "handler": FakeUpstreamHandler}
    finally:
        server.shutdown()
        server.server_close()


# ---------------- SSE 解析工具 ----------------


def parse_sse(text: str) -> list[Any]:
    """把 SSE 响应体解析为帧列表；`[DONE]` 解析为字符串 "[DONE]"，其余解析为 dict。"""
    frames: list[Any] = []
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if not block.startswith("data:"):
            continue
        data = block[len("data:") :].strip()
        frames.append("[DONE]" if data == "[DONE]" else json.loads(data))
    return frames


def sse_text(frames: list[Any]) -> str:
    return "".join(frame.get("content", "") for frame in frames if isinstance(frame, dict))


def auth_headers(client, username: str = "u_test_user", password: str = "pass123456") -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json={"username": username, "password": password})
    if response.status_code == 409:
        response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code in (200, 201), response.text
    return {"Authorization": f"Bearer {response.json()['data']['accessToken']}"}


# ---------------- 健康检查 ----------------


def test_health_reports_runtime_dirs(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "healthy"
    assert data["guestDailyChatLimit"] == 2
    # 只下发相对标签：服务器绝对路径（含用户名、宿主目录）绝不进入浏览器可见的明文
    assert data["dataDirLabel"] and data["modelsDirLabel"]
    assert not any(token in response.text for token in ("/" + "home/", "/root", "/tmp/", ":\\"))


# ---------------- 鉴权 ----------------


def test_register_login_me_logout_flow(client) -> None:
    created = client.post(
        "/api/v1/auth/register",
        json={"username": "flow_user", "password": "secret123", "displayName": "流程用户"},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["code"] == 201
    token = payload["data"]["accessToken"]
    assert payload["data"]["tokenType"] == "bearer"
    assert payload["data"]["user"]["isGuest"] is False

    duplicate = client.post("/api/v1/auth/register", json={"username": "flow_user", "password": "secret123"})
    assert duplicate.status_code == 409

    login = client.post("/api/v1/auth/login", json={"username": "flow_user", "password": "secret123"})
    assert login.status_code == 200 and login.json()["data"]["user"]["displayName"] == "流程用户"

    assert client.post("/api/v1/auth/login", json={"username": "flow_user", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "ghost_user", "password": "whatever"}).status_code == 401

    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["data"]["username"] == "flow_user"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    assert client.post("/api/v1/auth/logout").json()["data"]["loggedOut"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ab", "password": "secret123"},
        {"username": "bad name", "password": "secret123"},
        {"username": "good_user", "password": "123"},
    ],
)
def test_register_rejects_invalid_credentials(client, payload: dict[str, str]) -> None:
    assert client.post("/api/v1/auth/register", json=payload).status_code == 400


def test_protected_scenario_endpoints_require_login(client) -> None:
    headers = auth_headers(client, "scenario_owner")
    assert client.get("/api/v1/algorithms/scenarios").json()["data"] == []  # 游客：空列表 + 提示
    assert client.post("/api/v1/algorithms/scenarios", json={"kind": "banker", "name": "x", "payload": {}}).status_code == 401

    saved = client.post(
        "/api/v1/algorithms/scenarios",
        json={"kind": "banker", "name": "教材用例", "payload": {"available": [3, 3, 2]}},
        headers=headers,
    )
    assert saved.status_code == 201
    scenario_id = saved.json()["data"]["id"]
    listed = client.get("/api/v1/algorithms/scenarios?kind=banker", headers=headers).json()["data"]
    assert [row["name"] for row in listed] == ["教材用例"]
    assert listed[0]["payload"] == {"available": [3, 3, 2]}
    assert client.delete(f"/api/v1/algorithms/scenarios/{scenario_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/algorithms/scenarios/{scenario_id}", headers=headers).status_code == 404


# ---------------- 页面置换接口 ----------------


@pytest.mark.parametrize(
    "algorithm,expected_faults",
    [("FIFO", 15), ("LRU", 12), ("OPT", 9), ("CLOCK", 14)],
)
def test_page_replacement_returns_trace_with_textbook_fault_counts(client, algorithm: str, expected_faults: int) -> None:
    response = client.post(
        "/api/v1/algorithms/page-replacement/simulate",
        json={"algorithm": algorithm, "referenceString": FIFO_REFERENCE, "frameCount": 3},
    )
    assert response.status_code == 200
    trace = response.json()  # 设计文档：该接口直接返回 ExecutionTrace
    assert trace["algorithmId"] == algorithm.lower()
    assert trace["totalSteps"] == len(trace["steps"]) > 0
    assert trace["metrics"]["misses"] == expected_faults
    assert trace["metrics"]["hits"] == len(FIFO_REFERENCE) - expected_faults
    assert trace["metrics"]["totalAccess"] == len(FIFO_REFERENCE)
    assert trace["metrics"]["missRate"] == pytest.approx(expected_faults / len(FIFO_REFERENCE))
    assert trace["initialState"]["frameCount"] == 3
    assert trace["initialState"]["algorithm"] == algorithm
    assert len(trace["finalFrames"]) == 3
    for step in trace["steps"]:
        snapshot = step["snapshot"]
        assert len(snapshot["frames"]) == 3
        assert step["eventTone"] in {"NONE", "STEP", "HIT", "MISS", "SUCCESS", "DANGER", "BLOCK", "WAKEUP"}


def test_belady_anomaly_is_visible_through_api(client) -> None:
    def faults(frames: int) -> int:
        response = client.post(
            "/api/v1/algorithms/page-replacement/simulate",
            json={"algorithm": "FIFO", "referenceString": FIFO_REFERENCE, "frameCount": frames},
        )
        return response.json()["metrics"]["misses"]

    assert faults(3) == 15 and faults(4) == 10  # 页框变多反而缺页更少，异常点出现在 3→4


@pytest.mark.parametrize(
    "payload",
    [
        {"algorithm": "NRU", "referenceString": [1, 2], "frameCount": 3},
        {"algorithm": "FIFO", "referenceString": [], "frameCount": 3},
        {"algorithm": "FIFO", "referenceString": [1, 2], "frameCount": 1},
        {"algorithm": "FIFO", "referenceString": [1, 300], "frameCount": 3},
    ],
)
def test_page_replacement_invalid_inputs_return_400(client, payload: dict[str, Any]) -> None:
    response = client.post("/api/v1/algorithms/page-replacement/simulate", json=payload)
    assert response.status_code == 400
    assert "detail" in response.json()


# ---------------- 银行家接口 ----------------


BANKER_STATE = {
    "available": [3, 3, 2],
    "maxMatrix": [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]],
    "allocationMatrix": [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]],
}


def test_banker_safety_endpoint_returns_envelope_and_trace(client) -> None:
    response = client.post("/api/v1/algorithms/banker/check-safety", json=BANKER_STATE)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["isSafe"] is True
    assert data["safeSequence"] == ["P1", "P3", "P4", "P0", "P2"]
    assert data["steps"] == data["trace"]["steps"] and data["steps"]
    assert data["state"]["needMatrix"] == [[7, 4, 3], [1, 2, 2], [6, 0, 0], [0, 1, 1], [4, 3, 1]]


def test_banker_request_endpoint_grants_and_rolls_back(client) -> None:
    grant = client.post(
        "/api/v1/algorithms/banker/request-resource",
        json={"processIndex": 1, "requestVector": [1, 0, 2], "currentState": BANKER_STATE},
    )
    assert grant.status_code == 200
    data = grant.json()["data"]
    assert data["granted"] is True and data["resultingAvailable"] == [2, 3, 0]
    assert data["trace"]["algorithmId"] == "banker-request"

    denied = client.post(
        "/api/v1/algorithms/banker/request-resource",
        json={"processIndex": 4, "requestVector": [3, 3, 0], "currentState": BANKER_STATE},
    )
    body = denied.json()["data"]
    assert body["granted"] is False and body["isSafeAfterTentative"] is False
    assert body["trace"]["steps"][-1]["snapshot"]["phase"] == "ROLLBACK"


def test_banker_rejects_inconsistent_matrices(client) -> None:
    bad = {**BANKER_STATE, "allocationMatrix": [[9, 1, 0], *BANKER_STATE["allocationMatrix"][1:]]}
    response = client.post("/api/v1/algorithms/banker/check-safety", json=bad)
    assert response.status_code == 400
    assert "Max" in response.json()["detail"]


# ---------------- 多线程接口 ----------------


def test_threads_simulate_returns_replayable_trace(client) -> None:
    response = client.post(
        "/api/v1/algorithms/threads/simulate",
        json={"bufferCapacity": 5, "producerCount": 2, "consumerCount": 2, "totalOperations": 20},
    )
    assert response.status_code == 200
    trace = response.json()
    assert trace["algorithmId"] == "threads-pc"
    assert all(trace["invariants"].values())
    assert trace["metrics"]["produced"] == trace["metrics"]["consumed"] == 20
    assert trace["metrics"]["bufferRemaining"] == 0
    assert trace["metrics"]["mutexBlockEvents"] > 0  # 互斥锁争抢可观察
    actions = {step["snapshot"]["action"] for step in trace["steps"]}
    assert {"P_EMPTY", "P_MUTEX", "INSERT", "V_MUTEX", "V_FULL", "REMOVE", "BLOCK_MUTEX"} <= actions


@pytest.mark.parametrize(
    "payload",
    [
        {"bufferCapacity": 0, "producerCount": 1, "consumerCount": 1, "totalOperations": 5},
        {"bufferCapacity": 5, "producerCount": 9, "consumerCount": 1, "totalOperations": 5},
        {"bufferCapacity": 5, "producerCount": 1, "consumerCount": 1, "totalOperations": 999},
    ],
)
def test_threads_invalid_inputs_return_400(client, payload: dict[str, Any]) -> None:
    response = client.post("/api/v1/algorithms/threads/simulate", json=payload)
    assert response.status_code == 400


# ---------------- SSE 对话：内置 mock 后端 ----------------


def test_mock_chat_stream_frames_and_context_snapshot(client) -> None:
    response = client.post(
        CHAT_URL,
        json={
            "providerKey": "builtin-mock",
            "messages": [{"role": "user", "content": "帮我分析一下缺页情况"}],
            "contextSnapshot": {
                "pageReplacement": {"algorithm": "FIFO", "frameCount": 3, "hits": 5, "misses": 15, "missRate": 0.75, "frames": [7, 0, 1]},
                "banker": {"available": [3, 3, 2], "needMatrix": [[7, 4, 3]], "isSafe": True},
            },
            "conversationId": "conv-1",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse(response.text)
    assert isinstance(frames[0], dict) and frames[0]["type"] == "meta"
    assert frames[0]["provider"] == "builtin-mock"
    assert frames[0]["source"] == "builtin-mock"
    assert frames[0]["conversationId"] == "conv-1"
    assert frames[-1] == "[DONE]"
    assert frames[-2]["type"] == "done"
    deltas = [frame for frame in frames if isinstance(frame, dict) and frame["type"] == "delta"]
    assert len(deltas) > 3, "应当是逐块流式返回而不是一次性整包"
    text = sse_text(frames)
    assert "内置离线后端" in text or "内置演示助教" in text
    # 注入的算法快照必须出现在回答里，证明上下文的确被送进系统提示词
    assert "页面置换快照分析（FIFO）" in text
    assert "缺页率约 75.0%" in text
    assert "银行家算法快照分析" in text
    assert "Need[P0] = (7, 4, 3)" in text
    assert frames[0]["model"] == "osvis-mock-tutor"
    assert not any(isinstance(frame, dict) and frame.get("type") == "error" for frame in frames)


def test_mock_chat_without_context_uses_generic_tutorial(client) -> None:
    response = client.post(CHAT_URL, json={"providerKey": "builtin-mock", "messages": [{"role": "user", "content": "什么是死锁"}]})
    text = sse_text(parse_sse(response.text))
    assert "通用操作系统原理速览" in text
    assert "什么是死锁" in text


def test_chat_rejects_empty_messages_and_unknown_template(client) -> None:
    assert client.post(CHAT_URL, json={"messages": []}).status_code == 400
    assert client.post(CHAT_URL, json={"messages": [{"role": "user", "content": "hi"}], "providerKey": "no-such-vendor"}).status_code == 400


def test_chat_with_unknown_provider_id_returns_404(client) -> None:
    response = client.post(CHAT_URL, json={"messages": [{"role": "user", "content": "hi"}], "providerId": 999999})
    assert response.status_code == 404


# ---------------- 厂商配置：密钥掩码与加密落盘 ----------------


def test_provider_config_masks_key_and_never_returns_plaintext(client, tmp_root) -> None:
    secret = "sk-test-SECRET-abcdefghijklmnop"
    headers = auth_headers(client, "key_owner")
    saved = client.put(
        "/api/v1/ai/engine/providers",
        json={
            "providerKey": "openai",
            "displayName": "我的 OpenAI",
            "baseUrl": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "apiKey": secret,
            "extraHeaders": {"X-Tenant": "osvis"},
        },
        headers=headers,
    )
    assert saved.status_code == 200
    config = saved.json()["data"]
    assert config["hasApiKey"] is True
    assert secret not in saved.text
    masked = config["apiKeyMasked"]
    assert masked and secret not in masked
    assert masked.startswith(secret[:3]) and masked.endswith(secret[-3:])
    assert "*" in masked

    listed = client.get("/api/v1/ai/engine/providers", headers=headers)
    assert secret not in listed.text
    assert listed.json()["data"][0]["apiKeyMasked"] == masked

    # 留空 = 保留原密钥；显式空串 = 清除密钥
    kept = client.put(
        "/api/v1/ai/engine/providers",
        json={"providerKey": "openai", "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
        headers=headers,
    )
    assert kept.json()["data"]["hasApiKey"] is True and kept.json()["data"]["apiKeyMasked"] == masked
    cleared = client.put(
        "/api/v1/ai/engine/providers",
        json={"providerKey": "openai", "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o-mini", "apiKey": ""},
        headers=headers,
    )
    assert cleared.json()["data"]["hasApiKey"] is False and cleared.json()["data"]["apiKeyMasked"] == ""

    # 加密落盘：数据库里必须是密文，明文只出现在请求里
    client.put(
        "/api/v1/ai/engine/providers",
        json={"providerKey": "openai", "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o-mini", "apiKey": secret},
        headers=headers,
    )
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT api_key_cipher FROM provider_configs WHERE api_key_cipher != ''").fetchone()
    conn.close()
    assert row is not None
    cipher = row["api_key_cipher"]
    assert secret not in cipher
    from app.core.crypto import decrypt_secret

    assert decrypt_secret(cipher) == secret


def test_provider_configs_are_isolated_between_identities(client) -> None:
    guest_secret = "sk-guest-SECRET-0000000000"
    guest_saved = client.put(
        "/api/v1/ai/engine/providers",
        json={"providerKey": "deepseek", "baseUrl": "https://api.deepseek.com/v1", "model": "deepseek-chat", "apiKey": guest_secret},
    )
    assert guest_saved.status_code == 200
    guest_id = guest_saved.json()["data"]["id"]

    headers = auth_headers(client, "isolated_user")
    assert guest_secret not in client.get("/api/v1/ai/engine/providers", headers=headers).text
    assert all(row["providerKey"] != "deepseek" for row in client.get("/api/v1/ai/engine/providers", headers=headers).json()["data"])
    # 游客也不能访问别人的配置，且不能被游客激活/删除
    assert client.post(f"/api/v1/ai/engine/providers/{guest_id}/activate", headers=headers).status_code == 404
    assert client.delete(f"/api/v1/ai/engine/providers/{guest_id}", headers=headers).status_code == 404


def test_provider_config_validation_and_activation(client) -> None:
    headers = auth_headers(client, "activate_user")
    assert (
        client.put(
            "/api/v1/ai/engine/providers",
            json={"providerKey": "unknown-vendor", "baseUrl": "https://x.example.com/v1"},
            headers=headers,
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/api/v1/ai/engine/providers",
            json={"providerKey": "groq", "baseUrl": ""},
            headers=headers,
        ).status_code
        == 400
    )
    first = client.put(
        "/api/v1/ai/engine/providers",
        json={"providerKey": "groq", "baseUrl": "https://api.groq.com/openai/v1", "model": "llama-3.1-8b-instant"},
        headers=headers,
    ).json()["data"]
    second = client.put(
        "/api/v1/ai/engine/providers",
        json={"providerKey": "dashscope", "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
        headers=headers,
    ).json()["data"]
    activated = client.post(f"/api/v1/ai/engine/providers/{second['id']}/activate", headers=headers).json()["data"]
    assert activated["isActive"] is True
    rows = client.get("/api/v1/ai/engine/providers", headers=headers).json()["data"]
    active = [row["providerKey"] for row in rows if row["isActive"]]
    assert active == ["dashscope"]
    assert client.delete(f"/api/v1/ai/engine/providers/{first['id']}", headers=headers).status_code == 200


def test_engine_catalog_lists_twelve_templates_four_runtimes_and_mock(client) -> None:
    data = client.get("/api/v1/ai/engine/catalog").json()["data"]
    keys = [item["key"] for item in data["providers"]]
    assert len(keys) == 12
    for expected in ("openai", "anthropic", "gemini", "deepseek", "dashscope", "doubao", "siliconflow", "groq", "openrouter", "moonshot", "zhipu", "custom"):
        assert expected in keys
    assert {runtime["key"] for runtime in data["localRuntimes"]} == {"ollama", "lmstudio", "llamacpp", "vllm"}
    assert data["mock"]["key"] == "builtin-mock"
    assert data["guest"] == {"dailyChatLimit": 2, "isGuest": True}
    assert data["serverDefaults"]["hasServerKey"] is False


# ---------------- 连通性探测 ----------------


def test_ping_requires_base_url_and_reports_diagnostics(client, upstream) -> None:
    no_url = client.post("/api/v1/ai/engine/ping", json={"providerKey": "custom", "baseUrl": "", "model": "m"}).json()["data"]
    assert no_url["ok"] is False and no_url["errorCode"] == "NO_BASE_URL"
    assert client.post("/api/v1/ai/engine/ping", json={"providerKey": "nope", "baseUrl": "http://x"}).status_code == 400

    ok_probe = client.post("/api/v1/ai/engine/ping", json={"baseUrl": f"{upstream['base']}/v1", "model": "local-test-model"}).json()["data"]
    assert ok_probe["ok"] is True
    assert ok_probe["probePath"] == "/models"
    assert ok_probe["models"] == ["local-test-model"]
    assert ok_probe["modelExists"] is True
    assert ok_probe["latencyMs"] >= 0

    missing_model = client.post("/api/v1/ai/engine/ping", json={"baseUrl": f"{upstream['base']}/v1", "model": "not-there"}).json()["data"]
    assert missing_model["ok"] is True and missing_model["modelExists"] is False

    server_error = client.post("/api/v1/ai/engine/ping", json={"baseUrl": f"{upstream['base']}/v1/broken", "model": ""}).json()["data"]
    assert server_error["ok"] is False and server_error["errorCode"] == "UPSTREAM_5XX"


@pytest.mark.parametrize(
    "exception,expected_code",
    [("connect", "CONNECT_ERROR"), ("timeout", "TIMEOUT")],
)
def test_ping_maps_transport_failures_to_diagnostic_codes(client, monkeypatch, exception: str, expected_code: str) -> None:
    """连接被拒绝 / 超时必须转成可展示的诊断码，而不是 500。

    直接给 httpx 打桩，避免依赖"本机某个端口一定没人监听"这种环境假设。
    """
    import httpx

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        if exception == "connect":
            raise httpx.ConnectError("connection refused")
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom)
    data = client.post("/api/v1/ai/engine/ping", json={"baseUrl": "http://127.0.0.1:1/v1", "model": "m"}).json()["data"]
    assert data["ok"] is False
    assert data["errorCode"] == expected_code


def test_ping_uses_saved_config_and_key_without_exposing_it(client, upstream) -> None:
    secret = "sk-ping-SECRET-1234567890"
    upstream["handler"].auth_headers.clear()
    headers = auth_headers(client, "ping_user")
    saved = client.put(
        "/api/v1/ai/engine/providers",
        json={"providerKey": "openrouter", "baseUrl": f"{upstream['base']}/v1", "model": "local-test-model", "apiKey": secret},
        headers=headers,
    ).json()["data"]
    probed = client.post("/api/v1/ai/engine/ping", json={"providerId": saved["id"]}, headers=headers)
    assert probed.status_code == 200
    assert secret not in probed.text  # 密钥只存在于后端
    assert probed.json()["data"]["ok"] is True
    assert probed.json()["data"]["modelExists"] is True
    # 上游确实收到了后端解密出来的密钥（证明探测用的是保存的凭据）
    assert any(header == f"Bearer {secret}" for header in upstream["handler"].auth_headers)
    # 游客读不到别人的配置：直接 404，不泄露配置是否存在
    assert client.post("/api/v1/ai/engine/ping", json={"providerId": saved["id"]}).status_code == 404


def test_local_detect_reports_all_four_runtimes_offline(client) -> None:
    data = client.get("/api/v1/ai/engine/local/detect").json()["data"]
    runtimes = {runtime["key"]: runtime for runtime in data["runtimes"]}
    assert set(runtimes) == {"ollama", "lmstudio", "llamacpp", "vllm"}
    for runtime in runtimes.values():
        assert isinstance(runtime["online"], bool)
        assert isinstance(runtime.get("latencyMs"), (int, float)) or runtime.get("latencyMs") is None
    assert "loadingBackends" in data


def test_local_connect_rejects_unknown_runtime_and_offline_probe(client) -> None:
    assert client.post("/api/v1/ai/engine/local/connect", json={"runtimeKey": "nope"}).status_code == 400
    offline = client.post("/api/v1/ai/engine/local/connect", json={"runtimeKey": "vllm", "host": "127.0.0.1", "port": 9}).json()
    assert offline["data"]["connected"] is False
    assert offline["data"]["probe"]["online"] is False


def test_local_connect_saves_engine_when_service_online(client, upstream) -> None:
    port = urlparse(upstream["base"]).port
    result = client.post(
        "/api/v1/ai/engine/local/connect",
        json={"runtimeKey": "ollama", "host": "localhost", "port": port, "model": "", "save": True},
    )
    data = result.json()["data"]
    assert data["connected"] is True and data["saved"] is True
    assert data["model"] == "local-test-model"  # 服务端返回列表时自动选取第一个模型
    configs = client.get("/api/v1/ai/engine/providers").json()["data"]
    saved = [row for row in configs if row["id"] == data["configId"]][0]
    assert saved["isLocal"] is True and saved["hasApiKey"] is False and saved["isActive"] is True
    assert saved["providerKey"] == "ollama"
    # 保存的本地引擎可以直接用来发起对话（走 OpenAI 兼容流式接口）
    upstream["handler"].chatbot_payload = 'data: {"choices":[{"delta":{"content":"本地引擎"}}]}\n\ndata: [DONE]\n\n'.encode()
    chat = client.post(CHAT_URL, json={"providerId": saved["id"], "messages": [{"role": "user", "content": "hi"}]})
    frames = parse_sse(chat.text)
    assert frames[0]["source"] == "user-config" and frames[0]["provider"] == "ollama"
    assert sse_text(frames) == "本地引擎"
    # 测试自清理：删掉这条游客激活配置，避免影响后续"无显式引擎"的用例
    assert client.delete(f"/api/v1/ai/engine/providers/{saved['id']}").status_code == 200
    remaining = client.get("/api/v1/ai/engine/providers").json()["data"]
    assert all(row["id"] != saved["id"] for row in remaining)


# ---------------- 内置小模型五态管理 ----------------


def test_models_catalog_and_initial_status(client) -> None:
    catalog = client.get("/api/v1/ai/engine/models/catalog").json()["data"]
    assert len(catalog["models"]) == 4
    assert catalog["states"] == ["NOT_DOWNLOADED", "DOWNLOADING", "READY", "LOADING", "ERROR"]
    assert catalog["totalBytes"] == sum(model["bytesTotal"] for model in catalog["models"])
    assert all(model["sha256"] and model["downloadUrl"] and model["license"] for model in catalog["models"])

    status = client.get("/api/v1/ai/engine/models/status").json()["data"]
    by_id = {model["id"]: model for model in status["models"]}
    assert set(by_id) == {model["id"] for model in catalog["models"]}
    for model in status["models"]:
        assert model["state"] in catalog["states"]
        assert 0 <= model["percent"] <= 100
        assert model["bytesTotal"] > 0
    assert set(status["disk"]) >= {"files", "totalBytes", "directoryLabel"}
    assert not status["disk"]["directoryLabel"].startswith("/"), "模型的服务器绝对路径不得下发到浏览器"


def test_models_download_rejects_unknown_id_and_unlisted_host(client) -> None:
    assert client.post("/api/v1/ai/engine/models/download", json={"modelId": "no-such-model"}).status_code == 404
    blocked = client.post(
        "/api/v1/ai/engine/models/download",
        json={"modelId": "qwen2.5-0.5b-instruct", "sourceUrl": "https://evil.example.com/payload.gguf"},
    )
    assert blocked.status_code == 400
    assert "白名单" in blocked.json()["detail"]
    assert client.post("/api/v1/ai/engine/models/pause", json={"modelId": "no-such-model"}).status_code == 400


def _wait_for_state(client, model_id: str, states: set[str], timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        status = client.get("/api/v1/ai/engine/models/status").json()["data"]["models"]
        last = [model for model in status if model["id"] == model_id][0]
        if last["state"] in states:
            return last
        time.sleep(0.05)
    raise AssertionError(f"模型 {model_id} 未在 {timeout}s 内进入 {states}，当前状态：{last}")


def _shrink_expected_task(payload: bytes) -> None:
    """把内置模型的期望体积/SHA 换成测试载荷，便于离线验证 READY 路径（仅测试内改内存对象）。"""
    import hashlib

    from app.local_models.downloader import manager

    task = manager._tasks["qwen2.5-0.5b-instruct"]
    task.expected_bytes = len(payload)
    task.expected_sha256 = hashlib.sha256(payload).hexdigest()
    task.bytes_total = len(payload)


def test_model_download_lifecycle_ready_then_delete(client, upstream) -> None:
    handler = upstream["handler"]
    payload = (b"GGUF-test-payload-" * 4096) + bytes(range(256)) * 8
    handler.model_bytes = payload
    handler.slow_stream = False
    handler.range_requests.clear()
    _shrink_expected_task(payload)

    model_id = "qwen2.5-0.5b-instruct"
    started = client.post("/api/v1/ai/engine/models/download", json={"modelId": model_id, "sourceUrl": f"{upstream['base']}/v1/model.gguf"})
    assert started.status_code == 200 and started.json()["data"]["state"] == "DOWNLOADING"

    ready = _wait_for_state(client, model_id, {"READY", "ERROR"})
    assert ready["state"] == "READY", ready
    assert ready["bytesDone"] == len(payload) == ready["bytesTotal"]
    assert ready["percent"] == 100.0 and not ready["error"]

    disk = client.get("/api/v1/ai/engine/models/disk").json()["data"]
    entry = [row for row in disk["files"] if row["id"] == model_id][0]
    assert entry["bytes"] == len(payload)

    # 已下载的模型再点下载：无并发任务时重新校验，最终仍是 READY
    again = client.post("/api/v1/ai/engine/models/download", json={"modelId": model_id, "sourceUrl": f"{upstream['base']}/v1/model.gguf"})
    assert again.status_code == 200
    assert _wait_for_state(client, model_id, {"READY", "ERROR"})["state"] == "READY"

    # 下载完成后可以装载：本机没有可用推理后端，应得到明确的 LOAD_FAILED 诊断而不是 500
    loaded = client.post("/api/v1/ai/engine/models/load", json={"modelId": model_id})
    assert loaded.status_code == 200
    load_result = loaded.json()["data"]
    assert load_result["state"] in {"READY", "ERROR"}
    if load_result["state"] == "ERROR":
        # 装载失败但载荷仍在磁盘上：前端要能据此提供“重新装载”，而不是让人重下几百 MB
        assert load_result["errorCode"] == "LOAD_FAILED"
        assert load_result["downloaded"] is False
        assert load_result["fileOnDisk"] is True
        assert load_result["bytesOnDisk"] == len(payload)
        downloads_before = handler.download_requests
        recovered = client.post("/api/v1/ai/engine/models/retry", json={"modelId": model_id}).json()["data"]
        assert recovered["state"] == "READY" and recovered["percent"] == 100.0
        assert handler.download_requests == downloads_before, "载荷已校验过，retry 不应再发起网络下载"
        assert recovered["downloaded"] is True and recovered["fileOnDisk"] is True

    deleted = client.post("/api/v1/ai/engine/models/delete", json={"modelId": model_id})
    assert deleted.status_code == 200 and deleted.json()["data"]["state"] == "NOT_DOWNLOADED"
    assert client.get("/api/v1/ai/engine/models/disk").json()["data"]["totalBytes"] == 0
    assert client.post("/api/v1/ai/engine/models/load", json={"modelId": model_id}).status_code == 400


def test_model_download_pause_and_resume_with_range(client, upstream) -> None:
    handler = upstream["handler"]
    payload = b"RESUME-PAYLOAD-" * 24000  # 336 KB，配合 16KB 分块与慢速写入可可靠暂停
    handler.model_bytes = payload
    handler.slow_stream = True
    handler.range_requests.clear()
    _shrink_expected_task(payload)

    model_id = "qwen2.5-0.5b-instruct"
    client.post("/api/v1/ai/engine/models/download", json={"modelId": model_id, "sourceUrl": f"{upstream['base']}/v1/model.gguf"})
    time.sleep(0.2)
    paused = client.post("/api/v1/ai/engine/models/pause", json={"modelId": model_id}).json()["data"]
    assert paused["state"] == "NOT_DOWNLOADED" and paused["paused"] is True
    assert 0 < paused["bytesDone"] < len(payload)
    assert paused["errorCode"] in {"PAUSED", ""}

    handler.slow_stream = False
    resumed = client.post("/api/v1/ai/engine/models/retry", json={"modelId": model_id}).json()["data"]
    assert resumed["state"] == "DOWNLOADING"
    final = _wait_for_state(client, model_id, {"READY", "ERROR"})
    assert final["state"] == "READY", final
    assert handler.range_requests and handler.range_requests[0].startswith("bytes=")
    assert int(handler.range_requests[0].split("=")[1].split("-")[0]) == paused["bytesDone"]
    client.post("/api/v1/ai/engine/models/delete", json={"modelId": model_id})


def test_model_download_corrupted_payload_yields_error_state_and_cancel_cleans_up(client, upstream) -> None:
    payload = b"CORRUPT-ME-" * 20000
    upstream["handler"].model_bytes = payload
    upstream["handler"].slow_stream = False
    _shrink_expected_task(b"completely-different-content" * 1000)  # 期望 SHA 与真实报文不符

    model_id = "qwen2.5-0.5b-instruct"
    client.post("/api/v1/ai/engine/models/download", json={"modelId": model_id, "sourceUrl": f"{upstream['base']}/v1/model.gguf"})
    errored = _wait_for_state(client, model_id, {"ERROR"})
    assert "校验" in errored["error"] or "损坏" in errored["error"]
    assert errored["state"] == "ERROR"
    cancel = client.post("/api/v1/ai/engine/models/cancel", json={"modelId": model_id}).json()["data"]
    assert cancel["state"] == "NOT_DOWNLOADED" and cancel["bytesDone"] == 0


def test_models_status_persists_terminal_state_across_requests(client) -> None:
    """五态是持久化状态：重新读取 status / 直接查库都应看到同一份记录。"""
    states = {"NOT_DOWNLOADED", "DOWNLOADING", "READY", "LOADING", "ERROR"}
    status = client.get("/api/v1/ai/engine/models/status").json()["data"]["models"]
    assert all(model["state"] in states for model in status)
    by_id = {model["id"]: model for model in status}
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT model_id, state FROM model_records").fetchall()
    conn.close()
    known = {"qwen2.5-0.5b-instruct", "qwen2.5-1.5b-instruct", "deepseek-r1-distill-qwen-1.5b", "llama-3.2-1b-instruct"}
    assert {row["model_id"] for row in rows} <= known
    assert all(row["state"] in states for row in rows)
    # 落库状态必须与接口返回一致（下载任务结束时会持久化终态）
    for row in rows:
        assert row["state"] == by_id[row["model_id"]]["state"]


# ---------------- 游客额度与服务端密钥 ----


@pytest.fixture
def server_key_settings(client):
    """临时把"服务端默认密钥"打开并指向内置假上游。仅测试内改冻结配置对象。

    同时清空游客名下的引擎配置：服务端默认密钥路径要求"没有激活配置"，
    否则会优先走 user-config，测试结果会依赖用例执行顺序。
    """
    original_key = settings.server_api_key
    original_base = settings.server_base_url
    for row in client.get("/api/v1/ai/engine/providers").json()["data"]:
        client.delete(f"/api/v1/ai/engine/providers/{row['id']}")
    try:
        yield
    finally:
        object.__setattr__(settings, "server_api_key", original_key)
        object.__setattr__(settings, "server_base_url", original_base)


def test_guest_quota_blocks_after_limit_and_logged_in_user_is_exempt(client, upstream, server_key_settings) -> None:
    handler = upstream["handler"]
    chunks = [
        'data: {"choices":[{"delta":{"content":"网关"}}]}\n\n',
        'data: {"choices":[{"delta":{"content":"回答"}}]}\n\n',
        "data: [DONE]\n\n",
    ]
    handler.chatbot_payload = "".join(chunks).encode()
    handler.auth_headers.clear()
    object.__setattr__(settings, "server_api_key", "sk-server-side-secret")
    object.__setattr__(settings, "server_base_url", f"{upstream['base']}/v1")

    guest = {"X-Guest-Id": "quota-tester"}
    body = {"messages": [{"role": "user", "content": "你好"}]}
    first = client.post(CHAT_URL, json=body, headers=guest)
    assert first.status_code == 200
    frames = parse_sse(first.text)
    assert frames[0]["source"] == "server-default"
    assert sse_text(frames) == "网关回答"
    second = client.post(CHAT_URL, json=body, headers=guest)
    assert second.status_code == 200

    blocked = client.post(CHAT_URL, json=body, headers=guest)
    assert blocked.status_code == 429
    assert "额度" in blocked.json()["detail"]
    # 服务端密钥只在后端出现：应答里绝不能包含它
    assert "sk-server-side-secret" not in first.text

    other = client.post(CHAT_URL, json=body, headers={"X-Guest-Id": "another-guest"})
    assert other.status_code == 200

    headers = auth_headers(client, "quota_user")
    for _ in range(3):
        assert client.post(CHAT_URL, json=body, headers=headers).status_code == 200
    # 上游确实收到了后端注入的 Authorization 头（证明是后端代理转发而不是前端直连）
    assert all(header.startswith("Bearer sk-server-side-secret") for header in handler.auth_headers)


def test_server_default_upstream_error_is_reported_as_sse_error_frame(client, upstream, server_key_settings) -> None:
    object.__setattr__(settings, "server_api_key", "sk-server-side-secret")
    object.__setattr__(settings, "server_base_url", f"{upstream['base']}/v1/broken")
    response = client.post(CHAT_URL, json={"messages": [{"role": "user", "content": "hi"}]}, headers={"X-Guest-Id": "error-path"})
    assert response.status_code == 200
    frames = parse_sse(response.text)
    errors = [frame for frame in frames if isinstance(frame, dict) and frame["type"] == "error"]
    assert errors and errors[0]["code"] == "UPSTREAM_5XX"
    assert frames[-2]["type"] == "done"  # 出错也要正常收尾，SSE 以 [DONE] 终止
    assert frames[-1] == "[DONE]"
