import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SignupStatus(str, enum.Enum):
    pending_verification = "pending_verification"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"


class PendingSignup(Base):
    __tablename__ = "pending_signups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[SignupStatus] = mapped_column(Enum(SignupStatus), default=SignupStatus.pending_verification, nullable=False)

    verification_token: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    approval_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
