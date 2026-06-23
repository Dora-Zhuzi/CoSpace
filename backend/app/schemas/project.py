from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    folder_id: str


class ProjectOut(BaseModel):
    id: str
    name: str
    folder_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectUpdate(BaseModel):
    name: str


class CardCreate(BaseModel):
    conversation_id: str
    type: str = "viewpoint"
    title: str | None = None
    content: str


class CardUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    content: str | None = None


class PlanGenerate(BaseModel):
    conversation_id: str


class PlanItemCreate(BaseModel):
    name: str
    content: str


class PlanItemUpdate(BaseModel):
    name: str | None = None
    content: str | None = None


class ArticleItemCreate(BaseModel):
    name: str
    content: str


class ArticleItemUpdate(BaseModel):
    name: str | None = None
    content: str | None = None


class ConversationCreate(BaseModel):
    topic: str = ""


class MessageCreate(BaseModel):
    content: str


class TreeGenerate(BaseModel):
    plan_id: str


class TreeUpdate(BaseModel):
    name: str | None = None
    nodes: dict | None = None
