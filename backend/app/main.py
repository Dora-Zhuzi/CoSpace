import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import engine, Base
from app.api import auth, materials, projects
import app.models  # noqa: F401  确保所有模型被注册以建表

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 轻量补列：兼容已存在但缺少新列的旧库（新库由 create_all 直接建全，ALTER 会报重复列被忽略）
    migrations = [
        "ALTER TABLE draft_cards ADD COLUMN title VARCHAR",
        "ALTER TABLE draft_cards ADD COLUMN conversation_id VARCHAR",
        "ALTER TABLE draft_cards ADD COLUMN is_default INTEGER DEFAULT 0",
        "ALTER TABLE trees ADD COLUMN status VARCHAR DEFAULT 'ready'",
        "ALTER TABLE trees ADD COLUMN error VARCHAR",
        "ALTER TABLE projects ADD COLUMN article TEXT",
    ]
    for stmt in migrations:
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(stmt)
        except Exception:
            pass
    yield


app = FastAPI(title="DocGen MVP", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    from app.services.embedding import get_embedder
    from app.services.llm import get_llm

    return {
        "status": "ok",
        "llm": "remote" if get_llm().enabled else "local-fallback",
        "embedding_backend": get_embedder().backend,
    }


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(materials.router, prefix="/materials", tags=["materials"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
