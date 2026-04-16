from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/sections")
async def get_sections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = PermissionService(db)
    return {
        "sections": await service.get_effective_sections(current_user),
    }
