"""由共创讨论形成『写作方案』，再由方案生成可编辑的『结构树』。"""
import re
import uuid

from app.services.llm import get_llm


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


def _fallback_plan(title: str, cards: list[dict]) -> str:
    """本地模式：把方案卡片铺成结构化大纲（# 主题 / ## 章节 / ### 小节 + 描述）。"""
    plans = [c for c in cards if c.get("type") == "plan"]
    lines = [f"# {title}", "", "## 主体", ""]
    if plans:
        for i, c in enumerate(plans, 1):
            label = (c.get("title") or f"小节{i}").strip()
            lines.append(f"### {label}")
            lines.append((c.get("content") or "").strip() or "（依据草稿撰写本节内容）")
            lines.append("")
    else:
        lines += ["### 小节 1", "（依据草稿撰写本节内容）", ""]
    return "\n".join(lines).strip()


def generate_plan(title: str, cards: list[dict]) -> str:
    """基于讨论中沉淀的『方案』卡片，凝练出一份**结构化**写作方案。

    输出用 Markdown 分级标题表达文章结构：
      # 文章主题 / ## 章节 / ### 小节；每个小节标题下写"这节怎么写"。
    这个层级会被 generate_tree 确定性地解析成结构树。
    """
    llm = get_llm()
    if not llm.enabled:
        return _fallback_plan(title, cards)
    prompt = (
        "以下是用户在共创讨论中沉淀的写作方案草稿。请据此凝练出一份**结构化的写作方案**，"
        "用 Markdown 分级标题表达文章结构：\n"
        "- 一级标题（#）：文章主题；\n"
        "- 二级标题（##）：各章节标题；\n"
        "- 三级标题（###）：章节下的小节标题；\n"
        "- 每个三级小节标题**下面**用一段文字写清这一小节要写什么（写作要点/目标），"
        '必要时注明该小节的用途（如"用于论证""举一个案例""交代背景"）。\n'
        "严格要求：**只有三级小节标题下面才写描述文字；一级、二级标题下不写正文**；层级不超过 3 层。\n\n"
        f"文章主题：{title}\n\n草稿卡片：\n{_cards_text(cards)}"
    )
    try:
        return llm.chat(prompt).strip() or _fallback_plan(title, cards)
    except Exception:
        return _fallback_plan(title, cards)


# ---------------- 结构树 ----------------

def _attach_ids(node: dict) -> dict:
    return {
        "id": _new_id(),
        "label": str(node.get("label", "")).strip() or "未命名",
        "description": (node.get("description") or "").strip(),
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


def _parse_outline(plan: str, title: str) -> dict:
    """确定性解析写作方案的 markdown 标题层级为结构树。

    # → 文章主题（根）；## → 章节；### → 小节。
    小节标题下的文字 → 该小节的 description（含挂载提示等）。
    """
    root = {"label": title, "description": "", "children": []}
    level_nodes: dict[int, dict] = {1: root}
    current = root
    for raw in (plan or "").splitlines():
        s = raw.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            level = len(m.group(1))
            label = m.group(2).strip()
            if level == 1:
                if label:
                    root["label"] = label
                current = root
                level_nodes = {1: root}
            else:
                node = {"label": label or "未命名", "description": "", "children": []}
                parent_level = level - 1
                while parent_level >= 1 and parent_level not in level_nodes:
                    parent_level -= 1
                parent = level_nodes.get(parent_level, root)
                parent["children"].append(node)
                level_nodes[level] = node
                for deeper in [k for k in level_nodes if k > level]:
                    del level_nodes[deeper]
                current = node
        elif s:
            current["description"] = (
                f"{current['description']}\n{s}" if current["description"] else s
            )
    return root


def generate_tree(plan: str, title: str) -> dict:
    """确定性地把写作方案的标题层级解析成结构树（不再用 LLM 重组）。"""
    root = _parse_outline(plan or "", title)
    nodes = _attach_ids(root)
    if not nodes["children"]:
        return _fallback_tree(plan or "", title)
    return nodes
