import enum


class ConversationState(enum.StrEnum):
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    AWAITING_CLIENT_CONFIRMATION = "AWAITING_CLIENT_CONFIRMATION"
    WAITING_REVIEW = "WAITING_REVIEW"
    PAUSED = "PAUSED"
    HANDOFF = "HANDOFF"
    ERROR_REVIEW = "ERROR_REVIEW"


class BookingStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class BookingType(enum.StrEnum):
    INCALL = "incall"
    OUTCALL = "outcall"


class Channel(enum.StrEnum):
    SMS = "sms"
    WHATSAPP = "whatsapp"
    WORKER_APP = "worker_app"
    ADMIN_PANEL = "admin_panel"


class MessageDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SenderType(enum.StrEnum):
    CLIENT = "client"
    AGENT = "agent"
    WORKER = "worker"
    ADMIN = "admin"
    SYSTEM = "system"


class NotificationTargetType(enum.StrEnum):
    ADMIN = "admin"
    WORKER = "worker"
    CLIENT = "client"


class NotificationChannel(enum.StrEnum):
    IN_APP = "in_app"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"
    SYSTEM = "system"


class NotificationStatus(enum.StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    RETRY_PENDING = "retry_pending"
    DEAD_LETTER = "dead_letter"


class ActorType(enum.StrEnum):
    AGENT = "agent"
    ADMIN = "admin"
    WORKER = "worker"
    SYSTEM = "system"


class AwaitingReviewFrom(enum.StrEnum):
    ADMIN = "admin"
    WORKER = "worker"
    NONE = "none"


class InboundProvider(enum.StrEnum):
    TWILIO = "twilio"
