import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Source(str, enum.Enum):
    browser = "browser"
    file = "file"
    email = "email"
    calendar = "calendar"
    notion = "notion"
    obsidian = "obsidian"
    slack = "slack"
    github = "github"
    agent = "agent"


class Kind(str, enum.Enum):
    page = "page"
    document = "document"
    message = "message"
    event = "event"
    note = "note"
    code_file = "code_file"
    commit = "commit"


class EntityKind(str, enum.Enum):
    person = "person"
    project = "project"
    repo = "repo"
    org = "org"


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[Source] = mapped_column(Enum(Source), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[Kind] = mapped_column(Enum(Kind), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    url: Mapped[str | None] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_item_source"),)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[EntityKind] = mapped_column(Enum(EntityKind), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedded: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    item: Mapped["Item"] = relationship("Item", back_populates="chunks")


class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
