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
from app.services.parser import extract_text, split_paragraphs, chunk_labeled
from app.services.embedding import get_embedder
from app.services.llm import get_llm, parse_json

logger = logging.getLogger(__name__)

LABELS = ["观点", "论证", "案例", "其他"]
LABEL_DESC = (
    "观点=主张、结论、判断；"
    "论证=支撑观点的推理、分析、逻辑展开；"
    "案例=具体例子、故事、事件、数据实例；"
    "其他=背景、过渡、寒暄、无法归类的内容。"
)
LABEL_BATCH = 100  # 每批送 LLM 打标的段落数


def _label_paragraphs(paragraphs: list[str]) -> list[str]:
    """分批调 LLM 给每个段落标注类型（观点/论证/案例/其他）。无 LLM 时全标『其他』。"""
    n = len(paragraphs)
    llm = get_llm()
    if not llm.enabled or n == 0:
        return ["其他"] * n
    result = ["其他"] * n
    for start in range(0, n, LABEL_BATCH):
        batch = paragraphs[start:start + LABEL_BATCH]
        numbered = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(batch))
        prompt = (
            "下面是一份素材的若干段落（已编号）。请给每个段落标注一个类型，"
            "只能从这四类中选：\n"
            f"{LABEL_DESC}\n"
            '只返回 JSON 数组，每项形如 {"i":段号,"t":"类型"}，不要任何其它文字。\n\n'
            f"段落：\n{numbered}"
        )
        try:
            data = parse_json(llm.chat(prompt))
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    i, t = item.get("i"), item.get("t")
                    if isinstance(i, int) and 1 <= i <= len(batch) and t in LABELS:
                        result[start + i - 1] = t
        except Exception as e:
            logger.warning("label batch failed, keep 其他: %s", e)
    return result


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
    # 段落 → LLM 打类型标签 → 同类合并成 chunk（每块类型纯净）
    paragraphs = split_paragraphs(text)
    labels = _label_paragraphs(paragraphs)
    pieces = chunk_labeled(paragraphs, labels)  # [{content, type}]
    embedder = get_embedder()
    embeddings = embedder.encode_many([p["content"] for p in pieces])
    result = []
    for i, (piece, emb) in enumerate(zip(pieces, embeddings)):
        result.append(
            {
                "chunk_index": i,
                "content": piece["content"],
                "type": piece.get("type", "其他"),
                "summary": _summarize(piece["content"]),
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
                        type=c["type"],
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
