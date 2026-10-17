"""登录 / 注册 / 当前用户接口（设计文档第 11 章）。"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ...core import db
from ...core.security import AuthError, create_access_token, hash_password, validate_credentials, verify_password
from ...schemas.auth import LoginRequest, RegisterRequest
from ...schemas.common import ok
from ..deps import current_user_required

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> dict[str, Any]:
    try:
        validate_credentials(payload.username, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if db.get_user_by_username(payload.username) is not None:
        raise HTTPException(status_code=409, detail="用户名已被占用，请更换")
    try:
        user = db.create_user(payload.username, hash_password(payload.password), payload.displayName)
    except sqlite3.IntegrityError as exc:  # 并发注册兜底
        raise HTTPException(status_code=409, detail="用户名已被占用，请更换") from exc
    token, expires_in = create_access_token(user["id"], user["username"])
    return {
        "code": 201,
        "message": "注册成功",
        "data": {
            "accessToken": token,
            "tokenType": "bearer",
            "expiresIn": expires_in,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "displayName": user["displayName"],
                "isGuest": False,
            },
        },
    }


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    row = db.get_user_by_username(payload.username)
    if row is None or not verify_password(payload.password, row["password_hash"]):
        # 不区分"用户不存在"与"密码错误"，避免账号枚举
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, expires_in = create_access_token(int(row["id"]), row["username"])
    return ok(
        {
            "accessToken": token,
            "tokenType": "bearer",
            "expiresIn": expires_in,
            "user": {
                "id": int(row["id"]),
                "username": row["username"],
                "displayName": row["display_name"] or row["username"],
                "isGuest": False,
            },
        },
        message="登录成功",
    )


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user_required)) -> dict[str, Any]:
    return ok({"id": user["id"], "username": user["username"], "displayName": user["displayName"], "isGuest": False})


@router.post("/logout")
def logout() -> dict[str, Any]:
    # JWT 无状态：登出由前端清除本地令牌；此处仅作为显式契约端点
    return ok({"loggedOut": True}, message="已登出（前端请清除本地令牌）")
