"""素材入库管线：解析 → 切块 → 摘要 → 向量化 → 落库。

作为 FastAPI BackgroundTask 运行，自行开启数据库会话。
CPU/网络密集步骤通过 asyncio.to_thread 放到线程池，避免阻塞事件循环。
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.storage import storage
from app.models.material import Material, MaterialChunk
from app.services.parser import extract_text, chunk_text
from app.services.embedding import get_embedder
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


def _summarize(content: str) -> str:
    llm = get_llm()
    if not llm.enabled:
        # 降级：取首句/前 120 字作为摘要
        snippet = content.strip().replace("\n", " ")
        return snippet[:120]
    try:
        return llm.chat(
            content,
            system="你是文档助手，请用简洁中文对以下文本摘要，不超过200字。",
        ).strip() or content.strip()[:120]
    except Exception as e:
        logger.warning("summarize failed, fallback to snippet: %s", e)
        return content.strip().replace("\n", " ")[:120]


def _build_chunks(filename: str, data: bytes) -> list[dict]:
    text = extract_text(filename, data)
    if not text.strip():
        return []
    embedder = get_embedder()
    pieces = chunk_text(text)
    embeddings = embedder.encode_many(pieces)
    result = []
    for i, (content, emb) in enumerate(zip(pieces, embeddings)):
        result.append(
            {
                "chunk_index": i,
                "content": content,
                "summary": _summarize(content),
                "embedding": emb,
            }
        )
    return result


async def _set_status(db, material_id: str, status: str, error: str | None = None):
    mat = await db.get(Material, material_id)
    if mat:
        mat.status = status
        mat.error = error
        await db.commit()


async def index_material(material_id: str) -> None:
    async with SessionLocal() as db:
        try:
            mat = await db.get(Material, material_id)
            if not mat:
                return
            object_key = mat.object_key
            filename = mat.filename
            await _set_status(db, material_id, "indexing")

            data = await asyncio.to_thread(storage.get, object_key)
            chunks = await asyncio.to_thread(_build_chunks, filename, data)

            if not chunks:
                await _set_status(db, material_id, "index_failed", "未能从文件中提取到文本")
                return

            for c in chunks:
                db.add(
                    MaterialChunk(
                        material_id=material_id,
                        chunk_index=c["chunk_index"],
                        content=c["content"],
                        summary=c["summary"],
                        embedding=c["embedding"],
                    )
                )
            await db.commit()
            await _set_status(db, material_id, "indexed")
        except Exception as e:
            logger.exception("index_material failed: %s", e)
            await db.rollback()
            await _set_status(db, material_id, "index_failed", str(e)[:500])
