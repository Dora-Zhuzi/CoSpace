"""文章生成：遍历结构树，按每个节点挂载的素材片段逐节撰写，拼成 Markdown。"""
import asyncio
import logging

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.storage import storage
from app.models.material import Material, MaterialChunk
from app.models.project import Document, Tree
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


def _collect_chunk_ids(node: dict, acc: set) -> None:
    for cid in node.get("chunk_ids", []) or []:
        acc.add(cid)
    for child in node.get("children", []) or []:
        _collect_chunk_ids(child, acc)


def _write_section(label: str, chunks: list[dict]) -> str:
    if not chunks:
        return ""
    context = "\n\n".join(
        f"【来源：{c['file_name']}】\n{c['content']}" for c in chunks[:10]
    )
    llm = get_llm()
    if not llm.enabled:
        lines = [f"围绕「{label}」，依据挂载素材整理如下："]
        for c in chunks[:4]:
            snippet = c["content"].strip().replace("\n", " ")
            lines.append(f"- {snippet[:160]}（来源：{c['file_name']}）")
        return "\n".join(lines)
    prompt = (
        f'你是专业写作助手。请根据以下参考素材，为文章的"{label}"部分写一段内容。'
        "要求：紧扣该部分主题、逻辑清晰、语言流畅；充分利用素材，尽量使用原素材内容，"
        "原素材内容逻辑或语义断裂时才做少量内容补充和衔接；"
        "输出纯文本段落，不要重复标题。\n\n参考素材：\n" + context
    )
    try:
        return llm.chat(prompt).strip()
    except Exception as e:
        logger.warning("write_section failed: %s", e)
        return "\n".join(f"- {c['content'][:160]}" for c in chunks[:3])


def _rewrite_style(content: str, reference: str = "", strength: str = "light") -> str:
    """把文章按参考范文的风格改写；保留事实/结构，不新增信息。无 LLM 时原样返回。"""
    llm = get_llm()
    if not llm.enabled or not content.strip():
        return content
    ref = (reference or "").strip()
    if strength == "heavy":
        rule = (
            "完全按参考范文的行文风格重写：可大幅改写措辞、语气、节奏与段落组织；"
            "但必须保留初稿中的全部事实、数据、论点与章节结构，不得新增未提及的信息。"
        )
    else:
        rule = (
            "在保留初稿原有句子与结构的基础上做轻度风格化：主要调整语气、节奏、过渡与个别用词，"
            "使其更贴近参考范文的风格；不得改动事实、数据、论点，不得新增信息。"
        )
    ref_block = f"参考范文（模仿其行文风格）：\n{ref}\n\n" if ref else ""
    prompt = (
        "你是资深公众号编辑。请把下面的【文章初稿】改写成目标风格。\n"
        f"改写要求：{rule}\n"
        "保留 Markdown 的标题层级与顺序。直接输出改写后的完整 Markdown 全文，不要任何解释。\n\n"
        f"{ref_block}文章初稿：\n{content}"
    )
    try:
        out = llm.chat(prompt).strip()
        return out or content
    except Exception as e:
        logger.warning("rewrite_style failed: %s", e)
        return content


def _polish(markdown: str) -> str:
    """整篇连贯性润色：只加过渡、做小幅顺序微调，不改写正文实质内容。"""
    llm = get_llm()
    if not llm.enabled or not markdown.strip():
        return markdown
    prompt = (
        "下面是一篇由多个部分分别生成、再拼接而成的文章（Markdown）。"
        "请做一次轻度的连贯性润色，让各部分之间衔接更自然。严格遵守：\n"
        "1. 不要改写、删减或扩写正文的实质内容，不要新增事实或观点；\n"
        "2. 保留所有标题（# 的层级与文字）及其顺序，不要增删章节；\n"
        "3. 只允许：补充少量过渡句、在章节内小幅调整句子顺序；\n"
        "4. 直接输出完整的 Markdown 全文，不要任何解释或额外说明。\n\n"
        "文章：\n" + markdown
    )
    try:
        out = llm.chat(prompt).strip()
        # 防止模型误把文章改短/概括：明显变短则保留原文
        if out and len(out) >= len(markdown) * 0.6:
            return out
        return markdown
    except Exception as e:
        logger.warning("polish failed, keep original: %s", e)
        return markdown


def _render(node: dict, depth: int, chunk_map: dict) -> list[str]:
    out: list[str] = []
    label = node.get("label", "").strip() or "未命名"
    level = min(depth, 6)
    out.append(f"{'#' * level} {label}")

    chunks = [chunk_map[c] for c in (node.get("chunk_ids") or []) if c in chunk_map]
    if chunks:
        section = _write_section(label, chunks)
        if section:
            out.append(section)

    for child in node.get("children", []) or []:
        out.extend(_render(child, depth + 1, chunk_map))
    return out


async def generate_document(document_id: str, tree_id: str, project_id: str) -> None:
    async with SessionLocal() as db:
        try:
            doc = await db.get(Document, document_id)
            if not doc:
                return
            doc.status = "generating"
            await db.commit()

            tree = await db.get(Tree, tree_id)
            if not tree or tree.project_id != project_id:
                raise ValueError("结构树不存在")

            nodes = tree.nodes or {}

            # 预取所有被挂载的片段
            ids: set = set()
            _collect_chunk_ids(nodes, ids)
            chunk_map: dict = {}
            if ids:
                rows = await db.execute(
                    select(MaterialChunk.id, MaterialChunk.content, Material.filename)
                    .join(Material, Material.id == MaterialChunk.material_id)
                    .where(MaterialChunk.id.in_(ids))
                )
                for r in rows.all():
                    chunk_map[r[0]] = {"content": r[1], "file_name": r[2]}

            lines = await asyncio.to_thread(_render, nodes, 1, chunk_map)
            markdown = "\n\n".join(lines)

            # 全文衔接润色（仅加过渡/微调顺序，不改实质内容；无 LLM 时原样返回）
            markdown = await asyncio.to_thread(_polish, markdown)

            file_key = f"documents/{document_id}.md"
            await asyncio.to_thread(storage.put, file_key, markdown.encode("utf-8"))

            doc = await db.get(Document, document_id)
            doc.status = "done"
            doc.file_key = file_key
            # 生成即保存为一份文章
            from sqlalchemy import func
            from app.models.project import SavedArticle
            count = await db.execute(
                select(func.count()).select_from(SavedArticle).where(SavedArticle.project_id == project_id)
            )
            db.add(SavedArticle(project_id=project_id, name=f"文章 {count.scalar() + 1}", content=markdown))
            await db.commit()
        except Exception as e:
            logger.exception("generate_document failed: %s", e)
            await db.rollback()
            doc = await db.get(Document, document_id)
            if doc:
                doc.status = "failed"
                doc.error = str(e)[:500]
                await db.commit()
