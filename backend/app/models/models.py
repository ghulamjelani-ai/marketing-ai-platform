import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    firebase_uid: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), default="New Marketing Chat")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(back_populates="conversations")

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class FacebookConnection(Base):
    """The Facebook Page a user currently posts to. The Page token is stored encrypted.

    All Pages the user manages are kept in facebook_pages; this row is the chosen one.
    """

    __tablename__ = "facebook_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    page_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class PublishedPost(Base):
    """Every post that reached the user's Facebook Page (manual or scheduled)."""

    __tablename__ = "published_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(20), default="manual")
    message: Mapped[str] = mapped_column(Text, default="")
    with_image: Mapped[bool] = mapped_column(Boolean, default=False)
    facebook_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScheduledPost(Base):
    """A post handed to Facebook with a future publish time (Facebook publishes it)."""

    __tablename__ = "scheduled_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    message: Mapped[str] = mapped_column(Text, default="")
    with_image: Mapped[bool] = mapped_column(Boolean, default=False)

    # Publish time in UTC (naive datetime).
    run_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    # scheduled -> published | cancelled | removed
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    facebook_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recorded: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserMemory(Base):
    """A short profile of the user's business that the assistant remembers."""

    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(Text, default="")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class LoginOtp(Base):
    """The email code a Google sign-in must confirm. One row per Firebase user.

    Only a salted hash of the code is stored. `auth_time` ties the row to one
    Firebase sign-in, so a new sign-in needs a new code.
    """

    __tablename__ = "login_otps"

    firebase_uid: Mapped[str] = mapped_column(String(255), primary_key=True)
    auth_time: Mapped[int] = mapped_column(Integer, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), default="")
    salt: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set after 5 wrong codes: no checks and no new codes until this time.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OtpSendLog(Base):
    """One row per code email sent, for the hourly limits per email address and per IP."""

    __tablename__ = "otp_send_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ip: Mapped[str] = mapped_column(String(64), index=True, default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


class PasswordReset(Base):
    """A "forgot password" code for one email address. Only an HMAC of the code is kept."""

    __tablename__ = "password_resets"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    firebase_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), default="")
    salt: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FacebookPage(Base):
    """Every Page the user manages, saved when they connect, so they can choose one."""

    __tablename__ = "facebook_pages"
    __table_args__ = (UniqueConstraint("user_id", "page_id", name="uq_facebook_pages_user_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    page_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)



class UserPreference(Base):
    """Per-user settings. One row per user; a user without a row has the defaults."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class NotificationLog(Base):
    """What happened to each post email: sent, skipped (and why) or failed (and why).

    Only a short reason code is kept, never the SMTP password or the full message.
    """

    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    event: Mapped[str] = mapped_column(String(20), nullable=False)
    # sent | skipped | failed
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    detail: Mapped[str] = mapped_column(String(80), default="")
    preview: Mapped[str] = mapped_column(String(160), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
