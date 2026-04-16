from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repo import UserRepository


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 260000)
    return f"pbkdf2_sha256${salt}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, salt, digest_hex = stored_hash.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        260000,
    )
    return hmac.compare_digest(candidate.hex(), digest_hex)


class AuthError(Exception):
    pass


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)

    def _jwt_secret(self) -> bytes:
        # Keep a deterministic development fallback so local/test environments work.
        key = settings.secret_key or "dev-insecure-secret-change-me"
        return key.encode("utf-8")

    def _encode_jwt(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        signature = hmac.new(self._jwt_secret(), signing_input, hashlib.sha256).digest()
        return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"

    def decode_jwt(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError("Invalid token format")

        header_segment, payload_segment, signature_segment = parts
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected_sig = hmac.new(self._jwt_secret(), signing_input, hashlib.sha256).digest()
        try:
            actual_sig = _b64url_decode(signature_segment)
        except Exception as exc:  # pragma: no cover - defensive parsing guard
            raise AuthError("Invalid token signature") from exc
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise AuthError("Invalid token signature")

        try:
            payload_raw = _b64url_decode(payload_segment)
            payload = json.loads(payload_raw.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parsing guard
            raise AuthError("Invalid token payload") from exc
        if not isinstance(payload, dict):
            raise AuthError("Invalid token payload")
        exp = payload.get("exp")
        if not isinstance(exp, int):
            raise AuthError("Invalid token expiry")
        if datetime.now(UTC).timestamp() >= exp:
            raise AuthError("Token expired")
        return payload

    def _build_token(
        self,
        user: User,
        *,
        token_type: str,
        ttl_minutes: int,
        refresh_jti: str | None = None,
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "type": token_type,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        }
        if refresh_jti is not None:
            payload["rjti"] = refresh_jti
        return self._encode_jwt(payload)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            raise AuthError("Invalid credentials")
        if not verify_password(password, user.password_hash):
            raise AuthError("Invalid credentials")
        return user

    async def issue_token_pair(self, user: User) -> dict[str, Any]:
        refresh_jti = secrets.token_hex(16)
        await self.user_repo.touch_login(user, refresh_jti=refresh_jti)
        access_token = self._build_token(
            user,
            token_type="access",
            ttl_minutes=settings.access_token_ttl_minutes,
        )
        refresh_token = self._build_token(
            user,
            token_type="refresh",
            ttl_minutes=settings.refresh_token_ttl_minutes,
            refresh_jti=refresh_jti,
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role.value,
                "worker_id": str(user.worker_id) if user.worker_id else None,
            },
        }

    async def refresh_token_pair(self, refresh_token: str) -> dict[str, Any]:
        payload = self.decode_jwt(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthError("Invalid refresh token")

        user_id = payload.get("sub")
        rjti = payload.get("rjti")
        if not isinstance(user_id, str) or not isinstance(rjti, str):
            raise AuthError("Invalid refresh token payload")

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user or not user.is_active:
            raise AuthError("Invalid refresh token")
        if user.current_refresh_jti != rjti:
            raise AuthError("Refresh token has been invalidated")

        return await self.issue_token_pair(user)

    async def logout(self, refresh_token: str) -> None:
        payload = self.decode_jwt(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthError("Invalid refresh token")
        user_id = payload.get("sub")
        rjti = payload.get("rjti")
        if not isinstance(user_id, str) or not isinstance(rjti, str):
            raise AuthError("Invalid refresh token")

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user or user.current_refresh_jti != rjti:
            raise AuthError("Invalid refresh token")
        await self.user_repo.update_refresh_jti(user, None)

    async def get_user_from_access_token(self, token: str) -> User:
        payload = self.decode_jwt(token)
        if payload.get("type") != "access":
            raise AuthError("Invalid access token")
        user_id = payload.get("sub")
        role = payload.get("role")
        if not isinstance(user_id, str) or role not in {
            UserRole.ADMIN.value,
            UserRole.WORKER.value,
        }:
            raise AuthError("Invalid access token payload")

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user or not user.is_active:
            raise AuthError("User not found")
        return user
