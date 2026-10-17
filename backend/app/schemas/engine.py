"""模型引擎与 AI 对话接口结构（设计文档第 9、10 章）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32000)


class ChatStreamRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    contextSnapshot: dict[str, Any] | None = None
    providerId: int | None = Field(default=None, description="provider_configs 主键；省略则使用当前激活配置")
    providerKey: str | None = Field(default=None, description="厂商模板 key，用于未保存配置时直接试聊")
    model: str | None = None
    conversationId: str | None = None


class ProviderConfigIn(BaseModel):
    providerKey: str = Field(min_length=1, max_length=48)
    displayName: str | None = None
    baseUrl: str = Field(min_length=1, max_length=512)
    model: str = Field(default="", max_length=256)
    apiKey: str | None = Field(default=None, max_length=512, description="留空表示保留已存密钥；传空串表示清除")
    extraHeaders: dict[str, str] = Field(default_factory=dict)
    isLocal: bool = False

    @field_validator("extraHeaders")
    @classmethod
    def _limit_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20:
            raise ValueError("自定义请求头最多 20 项")
        return {str(k)[:64]: str(v)[:512] for k, v in value.items()}


class PingRequest(BaseModel):
    providerKey: str | None = None
    baseUrl: str | None = None
    model: str = ""
    apiKey: str | None = None
    extraHeaders: dict[str, str] = Field(default_factory=dict)
    providerId: int | None = None


class ModelDownloadRequest(BaseModel):
    modelId: str
    sourceUrl: str | None = Field(default=None, description="可选：覆盖下载地址（仍受主机白名单限制）")


class ModelIdRequest(BaseModel):
    modelId: str


class LocalConnectRequest(BaseModel):
    runtimeKey: str = Field(default="ollama", description="ollama / lmstudio / llamacpp / vllm")
    host: str = Field(default="localhost", max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    model: str = ""
    save: bool = Field(default=True, description="探测成功后是否保存为可用的本地厂商配置")
