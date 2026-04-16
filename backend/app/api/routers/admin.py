"""
Admin Panel API endpoints.
"""

import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.db.engine import get_db
from app.models.booking_media import BookingMedia
from app.models.enums import ActorType, BookingStatus, SectionKey, UserRole
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.booking_repo import BookingRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.notification_repo import NotificationRepository
from app.services.booking_service import BookingService
from app.services.permission_service import PermissionService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


class BookingActionNote(BaseModel):
    note: str | None = None


class SectionPermissionUpdateRequest(BaseModel):
    sections: dict[SectionKey, bool]


# ------------------------------------------------------------------
# Bookings
# ------------------------------------------------------------------


@router.get("/bookings")
async def list_bookings(
    status: BookingStatus | None = None,
    offset: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> Any:
    repo = BookingRepository(db)
    client_repo = ClientRepository(db)
    bookings = await repo.list_for_admin_queue(status=status, offset=offset, limit=limit)

    items: list[dict[str, Any]] = []
    for b in bookings:
        client = await client_repo.get_by_id(b.client_id)
        items.append(
            {
                "id": str(b.id),
                "status": b.status.value,
                "client_id": str(b.client_id),
                "client_phone_e164": client.phone_e164 if client else None,
                "worker_id": str(b.worker_id),
                "scheduled_start_at": b.scheduled_start_at.isoformat()
                if b.scheduled_start_at
                else None,
                "booking_type": b.booking_type.value if b.booking_type else None,
                "awaiting_review_from": b.awaiting_review_from.value,
                "created_at": b.created_at.isoformat(),
                "updated_at": b.updated_at.isoformat(),
            }
        )

    return [item for item in items]


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    repo = BookingRepository(db)
    client_repo = ClientRepository(db)
    booking = await repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    client = await client_repo.get_by_id(booking.client_id)
    media_result = await db.execute(
        select(BookingMedia).where(BookingMedia.booking_id == booking_id)
    )
    media_items = media_result.scalars().all()

    has_receipt = any(item.is_receipt for item in media_items)
    return {
        "id": str(booking.id),
        "status": booking.status.value,
        "client_id": str(booking.client_id),
        "client_phone_e164": client.phone_e164 if client else None,
        "worker_id": str(booking.worker_id),
        "session_id": str(booking.session_id),
        "booking_type": booking.booking_type.value if booking.booking_type else None,
        "scheduled_start_at": booking.scheduled_start_at.isoformat()
        if booking.scheduled_start_at
        else None,
        "scheduled_end_at": booking.scheduled_end_at.isoformat()
        if booking.scheduled_end_at
        else None,
        "duration_minutes": booking.duration_minutes,
        "client_age": booking.client_age,
        "client_ethnicity": booking.client_ethnicity,
        "client_name": booking.client_name,
        "outcall_address": booking.outcall_address,
        "price_total_gbp": str(booking.price_total_gbp) if booking.price_total_gbp else None,
        "advance_required_gbp": str(booking.advance_required_gbp)
        if booking.advance_required_gbp
        else None,
        "advance_received": booking.advance_received,
        "awaiting_review_from": booking.awaiting_review_from.value,
        "confirmed_at": booking.confirmed_at.isoformat() if booking.confirmed_at else None,
        "cancelled_at": booking.cancelled_at.isoformat() if booking.cancelled_at else None,
        "completed_at": booking.completed_at.isoformat() if booking.completed_at else None,
        "created_at": booking.created_at.isoformat(),
        "updated_at": booking.updated_at.isoformat(),
        "media_count": len(media_items),
        "has_receipt": has_receipt,
    }


@router.get("/bookings/{booking_id}/timeline")
async def get_booking_timeline(booking_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    booking_repo = BookingRepository(db)
    message_repo = MessageRepository(db)
    notification_repo = NotificationRepository(db)
    audit_repo = AuditRepository(db)
    from sqlalchemy import select

    from app.models.booking_media import BookingMedia

    booking = await booking_repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    messages = await message_repo.list_for_session(booking.session_id)
    notifications = await notification_repo.list_for_booking(booking_id)
    audits = await audit_repo.list_for_entity("booking", booking_id)
    media_result = await db.execute(
        select(BookingMedia).where(BookingMedia.booking_id == booking_id)
    )
    media_items = media_result.scalars().all()

    timeline: list[dict[str, Any]] = []
    for msg in messages:
        timeline.append(
            {
                "kind": "message",
                "timestamp": msg.created_at.isoformat(),
                "id": str(msg.id),
                "direction": msg.direction.value,
                "channel": msg.channel.value,
                "sender_type": msg.sender_type.value,
                "body": msg.body,
            }
        )

    for event in audits:
        timeline.append(
            {
                "kind": "audit",
                "timestamp": event.created_at.isoformat(),
                "id": str(event.id),
                "event_type": event.event_type,
                "actor_type": event.actor_type.value,
                "actor_ref": event.actor_ref,
                "metadata": event.metadata_,
            }
        )

    for notif in notifications:
        timeline.append(
            {
                "kind": "notification",
                "timestamp": notif.created_at.isoformat(),
                "id": str(notif.id),
                "target_type": notif.target_type.value,
                "target_ref": notif.target_ref,
                "template_key": notif.template_key,
                "status": notif.status.value,
                "send_at": notif.send_at.isoformat(),
            }
        )

    for media in media_items:
        timeline.append(
            {
                "kind": "media",
                "timestamp": media.created_at.isoformat(),
                "id": str(media.id),
                "channel": media.channel.value,
                "media_type": media.media_type,
                "source_url": media.source_url,
                "is_receipt": media.is_receipt,
            }
        )

    timeline.sort(key=lambda item: item["timestamp"])
    return {"booking_id": str(booking_id), "timeline": timeline}


@router.post("/bookings/{booking_id}/approve")
async def approve_booking(
    booking_id: uuid.UUID,
    body: BookingActionNote = BookingActionNote(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.ADMIN,
        note=body.note,
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.post("/bookings/{booking_id}/reject")
async def reject_booking(
    booking_id: uuid.UUID,
    body: BookingActionNote = BookingActionNote(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.REJECTED,
        actor_type=ActorType.ADMIN,
        note=body.note,
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: uuid.UUID,
    body: BookingActionNote = BookingActionNote(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.CANCELLED,
        actor_type=ActorType.ADMIN,
        note=body.note,
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.post("/bookings/{booking_id}/incall-address-sent")
async def mark_incall_address_sent(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.mark_incall_address_sent(
        booking_id=booking_id,
        actor_type=ActorType.ADMIN,
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {
        "booking_id": str(booking_id),
        "incall_address_sent_at": booking.incall_address_sent_at.isoformat()
        if booking and booking.incall_address_sent_at
        else None,
    }


@router.patch("/bookings/{booking_id}")
async def edit_booking(
    booking_id: uuid.UUID,
    updates: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    errors_all: list[str] = []
    for field, value in updates.items():
        _, errors = await svc.update_field(
            booking_id=booking_id,
            field_name=field,
            field_value=value,
            actor_type=ActorType.ADMIN,
        )
        errors_all.extend(errors)
    if errors_all:
        raise HTTPException(status_code=422, detail=errors_all)
    return {"booking_id": str(booking_id), "updated_fields": list(updates.keys())}


# ------------------------------------------------------------------
# Sessions
# ------------------------------------------------------------------


@router.get("/sessions/active")
async def list_active_sessions(db: AsyncSession = Depends(get_db)) -> Any:
    from sqlalchemy import select

    from app.models.conversation_session import ConversationSession
    from app.models.enums import ConversationState

    result = await db.execute(
        select(ConversationSession).where(
            ConversationSession.state.notin_([ConversationState.IDLE, ConversationState.PAUSED])
        )
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "client_id": str(s.client_id),
            "worker_id": str(s.worker_id),
            "state": s.state.value,
            "last_channel": s.last_channel.value if s.last_channel else None,
            "active_booking_id": str(s.active_booking_id) if s.active_booking_id else None,
        }
        for s in sessions
    ]


# ------------------------------------------------------------------
# Notifications
# ------------------------------------------------------------------


@router.get("/notifications")
async def list_notifications(db: AsyncSession = Depends(get_db)) -> Any:
    from datetime import datetime

    repo = NotificationRepository(db)
    notifications = await repo.list_queued_due(datetime.now(UTC))
    return [
        {
            "id": str(n.id),
            "target_type": n.target_type.value,
            "target_ref": n.target_ref,
            "template_key": n.template_key,
            "status": n.status.value,
            "send_at": n.send_at.isoformat(),
        }
        for n in notifications
    ]


# ------------------------------------------------------------------
# Agent control
# ------------------------------------------------------------------


@router.post("/agent/pause")
async def pause_agent(db: AsyncSession = Depends(get_db)) -> Any:
    from sqlalchemy import update

    from app.models.conversation_session import ConversationSession
    from app.models.enums import ConversationState

    await db.execute(
        update(ConversationSession)
        .where(ConversationSession.state.notin_([ConversationState.IDLE, ConversationState.PAUSED]))
        .values(state=ConversationState.PAUSED)
    )
    return {"paused": True}


@router.post("/agent/resume")
async def resume_agent(db: AsyncSession = Depends(get_db)) -> Any:
    from sqlalchemy import update

    from app.models.conversation_session import ConversationSession
    from app.models.enums import ConversationState

    await db.execute(
        update(ConversationSession)
        .where(ConversationSession.state == ConversationState.PAUSED)
        .values(state=ConversationState.IDLE)
    )
    return {"resumed": True}


# ------------------------------------------------------------------
# Users and section permissions
# ------------------------------------------------------------------


@router.get("/users/workers")
async def list_worker_users(db: AsyncSession = Depends(get_db)) -> Any:
    permission_service = PermissionService(db)
    workers = await permission_service.list_worker_users()
    return [
        {
            "id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "role": user.role.value,
            "worker_id": str(user.worker_id) if user.worker_id else None,
        }
        for user in workers
    ]


@router.get("/users/{user_id}/section-permissions")
async def get_worker_section_permissions(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    from app.repositories.user_repo import UserRepository

    user_repo = UserRepository(db)
    target_user = await user_repo.get_by_id(user_id)
    if not target_user or target_user.role != UserRole.WORKER:
        raise HTTPException(status_code=404, detail="Worker user not found")

    permission_service = PermissionService(db)
    sections = await permission_service.get_effective_sections(target_user)
    return {"user_id": str(target_user.id), "sections": sections}


@router.put("/users/{user_id}/section-permissions")
async def update_worker_section_permissions(
    user_id: uuid.UUID,
    body: SectionPermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    permission_service = PermissionService(db)
    try:
        sections = await permission_service.set_worker_permissions(
            worker_user_id=user_id,
            section_updates=body.sections,
            updated_by_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"user_id": str(user_id), "sections": sections}
