import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, JSON, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class Project(Base):
    """一个『AI 共创写作项目』，绑定一个素材库。"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    folder_id: Mapped[str] = mapped_column(
        String, ForeignKey("material_folders.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Conversation(Base):
    """一次 AI 共创讨论会话。"""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String, nullable=False)
    # 开场注入的素材摘要快照（建会话时一次性生成）
    context: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DraftCard(Base):
    """共创讨论中沉淀的草稿卡片：方案 / 观点 / 问题 / 案例（均可多个）。

    是后续『写作方案』的设计基础。
    """

    __tablename__ = "draft_cards"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 草稿便签按「讨论」归属
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True
    )
    # plan / viewpoint / case
    type: Mapped[str] = mapped_column(String, nullable=False, default="viewpoint")
    # 方案卡片的自定义名称（其它类型可为空）
    title: Mapped[str] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 默认卡片（观点/案例/草稿）不可删除；用户自建的可删
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class WritingPlan(Base):
    """用户手动保存的写作方案（一个项目可有多份）。"""

    __tablename__ = "writing_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Tree(Base):
    """可编辑的文章结构树。

    nodes 结构（递归）：
      { "id": str, "label": str, "children": [...], "chunk_ids": [str, ...] }
    chunk_ids 即挂载到该节点的素材片段（片段级挂载）。
    """

    __tablename__ = "trees"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    nodes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # generating / ready / failed（生成结构并自动挂载素材）
    status: Mapped[str] = mapped_column(String, nullable=False, default="ready")
    error: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SavedArticle(Base):
    """用户手动保存的文章（一个项目可有多份）。"""

    __tablename__ = "saved_articles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    tree_id: Mapped[str] = mapped_column(
        String, ForeignKey("trees.id", ondelete="CASCADE"), nullable=False
    )
    # pending / generating / done / failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    file_key: Mapped[str] = mapped_column(String, nullable=True)
    error: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
