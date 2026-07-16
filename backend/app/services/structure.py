"""由写作方案生成结构树，并自动从素材库筛选、挂载素材到节点。

流程（后台任务）：
1. 用写作方案生成结构（authoring.generate_tree）。
2. 取项目素材库全部 chunk。
3. 每个叶子节点用 embedding 取 top-N 候选 chunk（粗筛），再交给 LLM 精选真正适用的（精挂）。
4. 写回各节点 chunk_ids，置 tree.status=ready。
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.project import Tree, Project
from app.models.material import Material, MaterialChunk
from app.services import authoring
from app.services.embedding import get_embedder, cosine
from app.services.llm import get_llm, parse_json

logger = logging.getLogger(__name__)

N_CANDIDATES = 20        # （保留）
PER_TYPE_CANDIDATES = 8  # 候选池每种类型各取相似度 top-K，保证每类型都有代表
K_FALLBACK = 5           # 无 LLM 时每节点保留数
MIN_MOUNT = 6            # 每节点保底挂载数：LLM 挑不足时用相似度最高的候选补齐


def _leaves(node: dict, path: list[str], acc: list[dict]) -> None:
    children = node.get("children") or []
    label = node.get("label", "")
    p = path + [label] if label else path
    if not children:
        acc.append({
            "id": node.get("id"),
            "label": label,
            "path": " > ".join(p),
            "description": node.get("description", ""),
        })
    else:
        for c in children:
            _leaves(c, p, acc)


def _select_for_node(leaf: dict, candidates: list[tuple]) -> list[str]:
    """candidates: [(chunk, score)]。让 LLM 先判断该小节需要哪些类型的素材，
    再灵活挑选（可跨多种类型、同一类型可多条）。返回选中的 chunk_id 列表。"""
    llm = get_llm()
    if not llm.enabled:
        return [c["id"] for c, _ in candidates[:K_FALLBACK]]
    listing = "\n".join(
        f"{c['id']} [{c.get('type', '其他')}]: {(c.get('summary') or (c.get('content') or '')[:120])}"
        for c, _ in candidates
    )
    prompt = (
        "你在为一篇文章的某个小节挑选素材。素材分四类：观点、论证、案例、其他。\n"
        "请：①先根据该小节的写作要求，判断它需要哪些类型的素材（可以是多种）；"
        "②再从候选中挑出适用的素材——**可跨多种类型、同一类型也可多条**，按相关度从高到低排列；"
        "都不合适返回 []。\n"
        '只返回素材编号的 JSON 数组（如 ["a","b"]），不要其它文字。\n\n'
        f"小节位置：{leaf['path']}\n"
        f"小节写作要求：{leaf.get('description') or '（未提供，按小节标题相关性判断）'}\n\n"
        f"候选素材（格式 = 编号 [类型]: 摘要）：\n{listing}"
    )
    try:
        data = parse_json(llm.chat(prompt))
        ids = data if isinstance(data, list) else (data.get("ids", []) if isinstance(data, dict) else [])
        cand_ids = {c["id"] for c, _ in candidates}
        return [i for i in ids if i in cand_ids]
    except Exception as e:
        logger.warning("LLM select_for_node failed, fallback: %s", e)
        return [c["id"] for c, _ in candidates[:K_FALLBACK]]


def mount_chunks(nodes: dict, plan: str, chunks: list[dict]) -> dict:
    leaves: list[dict] = []
    _leaves(nodes, [], leaves)
    if not leaves or not chunks:
        return nodes

    embedder = get_embedder()
    assignments: dict[str, list[str]] = {}
    for leaf in leaves:
        # 用小节的写作要求做语义查询（无则退回小节路径/标题）
        query = leaf.get("description") or leaf["path"] or leaf["label"]
        node_emb = embedder.encode(query)
        scored_all = sorted(
            ((ch, cosine(ch.get("embedding"), node_emb)) for ch in chunks),
            key=lambda x: x[1],
            reverse=True,
        )
        # 候选池：每种类型各取相似度 top-K，保证各类型都有代表进池
        per_type: dict[str, int] = {}
        candidates: list[tuple] = []
        for ch, s in scored_all:
            t = ch.get("type", "其他")
            if per_type.get(t, 0) < PER_TYPE_CANDIDATES:
                candidates.append((ch, s))
                per_type[t] = per_type.get(t, 0) + 1
        chosen = _select_for_node(leaf, candidates)
        # 保底：LLM 挑不足 MIN_MOUNT 条时，用相似度最高的候选补齐
        if len(chosen) < MIN_MOUNT:
            picked = set(chosen)
            for ch, _ in scored_all:
                if ch["id"] not in picked:
                    chosen.append(ch["id"])
                    picked.add(ch["id"])
                    if len(chosen) >= MIN_MOUNT:
                        break
        if chosen:
            assignments[leaf["id"]] = chosen

    def walk(n: dict) -> None:
        n["chunk_ids"] = assignments.get(n.get("id"), [])
        for c in n.get("children") or []:
            walk(c)

    walk(nodes)
    return nodes


async def build_tree(tree_id: str, project_id: str, plan: str) -> None:
    async with SessionLocal() as db:
        try:
            project = await db.get(Project, project_id)
            if not project:
                return

            nodes = await asyncio.to_thread(authoring.generate_tree, plan or "", project.name)

            rows = await db.execute(
                select(
                    MaterialChunk.id,
                    MaterialChunk.content,
                    MaterialChunk.summary,
                    MaterialChunk.embedding,
                    MaterialChunk.type,
                )
                .join(Material, Material.id == MaterialChunk.material_id)
                .where(Material.folder_id == project.folder_id)
            )
            chunks = [
                {"id": r[0], "content": r[1], "summary": r[2], "embedding": r[3], "type": r[4] or "其他"}
                for r in rows.all()
            ]

            nodes = await asyncio.to_thread(mount_chunks, nodes, plan, chunks)

            tree = await db.get(Tree, tree_id)
            if tree:
                tree.nodes = nodes
                tree.name = nodes.get("label", project.name)
                tree.status = "ready"
                await db.commit()
        except Exception as e:
            logger.exception("build_tree failed: %s", e)
            await db.rollback()
            tree = await db.get(Tree, tree_id)
            if tree:
                tree.status = "failed"
                tree.error = str(e)[:500]
                await db.commit()
