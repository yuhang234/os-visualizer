"""通用传输结构：统一响应信封。

设计文档第 13.2 节中 auth 与 banker 接口显式使用 `{ "code": 200, "data": {...} }`；
本模块提供统一信封，额外带 `message` 字段（便于前端直接展示错误原因）。
算法轨迹类接口（page-replacement / threads）按文档原文直接返回 ExecutionTrace。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200, description="业务状态码，与 HTTP 状态码保持一致")
    message: str = Field(default="ok")
    data: T | None = None


class ErrorResponse(BaseModel):
    code: int
    message: str
    detail: Any | None = None


def ok(data: Any, message: str = "ok") -> dict[str, Any]:
    return {"code": 200, "message": message, "data": data}


def created(data: Any, message: str = "created") -> dict[str, Any]:
    return {"code": 201, "message": message, "data": data}
