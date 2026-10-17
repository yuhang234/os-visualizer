"""鉴权接口请求/响应结构（设计文档第 11 章）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    displayName: str | None = Field(default=None, max_length=64)


class UserInfo(BaseModel):
    id: int
    username: str
    displayName: str = ""
    isGuest: bool = False


class TokenPayload(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    expiresIn: int
    user: UserInfo
