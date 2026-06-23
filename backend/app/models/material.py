import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class MaterialFolder(Base):
    __tablename__ = "material_folders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    materials: Mapped[list["Material"]] = relationship(
        "Material", back_populates="folder", cascade="all, delete-orphan", lazy="raise"
    )


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    folder_id: Mapped[str] = mapped_column(
        String, ForeignKey("material_folders.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    object_key: Mapped[str] = mapped_column(String, nullable=False)
    # uploading / upload_failed / upload_success / indexing / indexed / index_failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploading")
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    folder: Mapped["MaterialFolder"] = relationship(
        "MaterialFolder", back_populates="materials", lazy="raise"
    )
    chunks: Mapped[list["MaterialChunk"]] = relationship(
        "MaterialChunk", cascade="all, delete-orphan", lazy="raise"
    )


class MaterialChunk(Base):
    __tablename__ = "material_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    material_id: Mapped[str] = mapped_column(
        String, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    # 真正存储向量：list[float]，用于主题打分与检索
    embedding: Mapped[list] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
