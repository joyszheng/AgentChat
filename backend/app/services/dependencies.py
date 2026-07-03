"""认证依赖和权限验证。"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..services.auth import decode_access_token


logger = logging.getLogger("uvicorn.error")

# HTTP Bearer 认证方案
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
):
    """获取当前登录用户（可选）。

    Args:
        credentials: HTTP Bearer 凭证
        db: 数据库会话

    Returns:
        User | None: 当前用户，未登录返回 None
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        return None

    username: str = payload.get("sub")
    if username is None:
        return None

    user = crud.get_user_by_username(db, username)
    if user is None or not user.is_active:
        return None

    return user


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
):
    """要求用户已登录。

    Args:
        credentials: HTTP Bearer 凭证
        db: 数据库会话

    Returns:
        User: 当前用户

    Raises:
        HTTPException: 未登录或令牌无效
    """
    logger.debug(f"[auth] require_auth called, credentials={credentials}")

    if credentials is None:
        logger.warning("[auth] No credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录，请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌格式错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = crud.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return user


async def require_admin(
    user = Depends(require_auth),
):
    """要求用户是管理员。

    Args:
        user: 当前用户

    Returns:
        User: 当前管理员用户

    Raises:
        HTTPException: 不是管理员
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )

    return user
