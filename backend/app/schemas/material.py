from datetime import datetime
from pydantic import BaseModel


class FolderCreate(BaseModel):
    name: str


class FolderUpdate(BaseModel):
    name: str


class MaterialOut(BaseModel):
    id: str
    filename: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FolderOut(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FolderDetail(FolderOut):
    materials: list[MaterialOut] = []
