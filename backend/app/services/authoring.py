"""由共创讨论形成『写作方案』，再由方案生成可编辑的『结构树』。"""
import re
import uuid

from app.services.llm import get_llm, parse_json


def _new_id() -> str:
    return "n-" + uuid.uuid4().hex[:8]


# ---------------- 写作方案 ----------------

CARD_TYPE_LABEL = {
    "plan": "方案",
    "viewpoint": "观点",
    "case": "案例",
}


def _cards_text(cards: list[dict]) -> str:
    lines = []
    for c in cards:
        label = CARD_TYPE_LABEL.get(c.get("type", ""), "卡片")
        title = c.get("title")
        head = f"{label}：{title}" if (c.get("type") == "plan" and title) else label
        lines.append(f"【{head}】{c.get('content', '').strip()}")
    return "\n".join(lines)


def generate_plan(title: str, cards: list[dict]) -> str:
    """基于共创讨论中沉淀的草稿卡片（方案/观点/问题/案例）凝练写作方案。"""
    llm = get_llm()
    if not llm.enabled:
        def pick(t):
            return [c["content"].strip() for c in cards if c.get("type") == t]
        plans, views, cases = pick("plan"), pick("viewpoint"), pick("case")
        def bullets(items):
            return "\n".join(f"- {x[:100]}" for x in items) or "- （暂无）"
        return (
            f"# 写作方案：{title}\n\n"
            f"## 核心观点\n{bullets(views or plans)}\n\n"
            f"## 内容范围\n{bullets(cases)}\n\n"
            f"## 组织思路\n引言 → 主体论述 → 总结。\n\n"
            "（本地模式生成，配置大模型后将依据草稿卡片自动凝练。）"
        )
    prompt = (
        "以下是用户在共创讨论中沉淀的草稿卡片（含方案、观点、问题、案例）。"
        "请据此凝练出一份**写作方案**，用 Markdown 输出，包含三部分："
        "## 核心观点、## 内容范围、## 组织思路。简洁、可执行，充分吸收这些卡片的内容。\n\n"
        f"草稿卡片：\n{_cards_text(cards)}"
    )
    try:
        return llm.chat(prompt).strip()
    except Exception:
        return f"# 写作方案：{title}\n\n## 核心观点\n（生成失败，请重试）"


# ---------------- 结构树 ----------------

def _attach_ids(node: dict) -> dict:
    return {
        "id": _new_id(),
        "label": str(node.get("label", "")).strip() or "未命名",
        "chunk_ids": [],
        "children": [_attach_ids(c) for c in node.get("children", []) if isinstance(c, dict)],
    }


def _fallback_tree(plan: str, title: str) -> dict:
    """从方案 markdown 的标题/列表项粗略提取章节；提取不到则给默认骨架。"""
    sections: list[dict] = []
    for line in plan.splitlines():
        s = line.strip()
        m = re.match(r"^#{1,6}\s+(.*)$", s)
        if m:
            label = m.group(1).strip()
            if label and not label.startswith("写作方案"):
                sections.append({"label": label, "children": []})
    if len(sections) < 2:
        sections = [
            {"label": "引言", "children": []},
            {"label": "主体论述", "children": []},
            {"label": "总结", "children": []},
        ]
    return _attach_ids({"label": title, "children": sections})


def generate_tree(plan: str, title: str) -> dict:
    llm = get_llm()
    if not llm.enabled or not (plan and plan.strip()):
        return _fallback_tree(plan or "", title)
    prompt = (
        "根据以下写作方案，生成文章的结构树（多级章节大纲）。"
        '只返回 JSON：{"title":"文章标题","children":[{"label":"章节名","children":[{"label":"子节点"}]}]}。'
        "层级不超过3层，章节精炼。\n\n写作方案：\n" + plan
    )
    try:
        data = parse_json(llm.chat(prompt))
        root = {
            "label": data.get("title") or title,
            "children": data.get("children", []),
        }
        nodes = _attach_ids(root)
        if not nodes["children"]:
            return _fallback_tree(plan, title)
        return nodes
    except Exception:
        return _fallback_tree(plan, title)
