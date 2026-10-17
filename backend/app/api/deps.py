"""FastAPI 依赖：可选鉴权、强制鉴权、客户端标识。"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from ..core import db
from ..core.security import decode_access_token

BEARER_PREFIX = "bearer "


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    value = authorization.strip()
    if value.lower().startswith(BEARER_PREFIX):
        return value[len(BEARER_PREFIX) :].strip()
    return value


def current_user_optional(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    """未登录返回 None（游客模式），令牌无效同样返回 None，不抛异常。"""
    token = _extract_token(authorization)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    row = db.get_user_by_id(int(user_id))
    if row is None:
        return None
    return {"id": int(row["id"]), "username": row["username"], "displayName": row["display_name"] or row["username"]}


def current_user_required(user: dict[str, Any] | None = Depends(current_user_optional)) -> dict[str, Any]:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录后访问该接口",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def client_key(
    request: Request,
    user: dict[str, Any] | None = Depends(current_user_optional),
    x_guest_id: str | None = Header(default=None, alias="X-Guest-Id"),
) -> str:
    """游客额度计数用的客户端标识：登录用户按用户计，游客按浏览器实例 + IP 计。"""
    if user is not None:
        return f"user:{user['id']}"
    host = request.client.host if request.client else "unknown"
    guest = (x_guest_id or "").strip()[:64]
    return f"guest:{host}:{guest}" if guest else f"guest:{host}"
