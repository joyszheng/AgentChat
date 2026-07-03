"""用户认证路由。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..services.auth import create_access_token, verify_password
from ..services.dependencies import get_current_user, require_auth


logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(login_data: schemas.UserLogin, db: Session = Depends(get_db)):
    """用户登录，返回 JWT 令牌。"""
    user = crud.get_user_by_username(db, login_data.username)

    if user is None or not verify_password(login_data.password, user.password_hash):
        logger.warning("[auth] Login failed for username=%s", login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 创建 JWT 令牌
    access_token = create_access_token(data={"sub": user.username})

    logger.info("[auth] User logged in username=%s role=%s", user.username, user.role)

    return schemas.TokenResponse(
        access_token=access_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserResponse | None)
def get_current_user_info(user=Depends(get_current_user)):
    """获取当前登录用户信息（可选认证）。"""
    if user is None:
        return None

    return schemas.UserResponse.model_validate(user)


@router.post("/logout")
def logout(user=Depends(require_auth)):
    """用户登出（客户端需清除 token）。"""
    logger.info("[auth] User logged out username=%s", user.username)
    return {"message": "登出成功"}
