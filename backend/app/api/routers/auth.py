from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


@router.post("/login")
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)) -> Any:
    service = AuthService(db)
    try:
        user = await service.authenticate(body.email, body.password)
        return await service.issue_token_pair(user)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh(body: RefreshBody, db: AsyncSession = Depends(get_db)) -> Any:
    service = AuthService(db)
    try:
        return await service.refresh_token_pair(body.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout")
async def logout(body: RefreshBody, db: AsyncSession = Depends(get_db)) -> Any:
    service = AuthService(db)
    try:
        await service.logout(body.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)) -> Any:
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role.value,
        "worker_id": str(current_user.worker_id) if current_user.worker_id else None,
    }
