import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.storage import storage
from app.models.user import User
from app.models.project import Project, Conversation, Message, DraftCard, WritingPlan, SavedArticle, Tree, Document
from app.models.material import MaterialFolder, Material, MaterialChunk
from app.schemas.project import (
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    PlanGenerate,
    PlanItemCreate,
    PlanItemUpdate,
    ArticleItemCreate,
    ArticleItemUpdate,
    CardCreate,
    CardUpdate,
    ConversationCreate,
    MessageCreate,
    TreeGenerate,
    TreeUpdate,
)
from app.services import chat as chat_svc
from app.services import authoring
from app.services.generator import generate_document
from app.services.indexer import index_material
from app.services.structure import build_tree

router = APIRouter()

CONTEXT_CHAR_LIMIT = 6000


async def _get_owned_project(db: AsyncSession, project_id: str, user: User) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def _build_context(db: AsyncSession, folder_id: str) -> str:
    rows = await db.execute(
        select(Material.filename, MaterialChunk.summary)
        .join(MaterialChunk, MaterialChunk.material_id == Material.id)
        .where(Material.folder_id == folder_id, MaterialChunk.summary.isnot(None))
        .order_by(Material.created_at, MaterialChunk.chunk_index)
    )
    parts: list[str] = []
    total = 0
    for filename, summary in rows.all():
        line = f"【{filename}】{summary}"
        total += len(line)
        if total > CONTEXT_CHAR_LIMIT:
            break
        parts.append(line)
    return "\n".join(parts)


# ---------------- 素材库选择 ----------------

@router.get("/available-folders")
async def list_available_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folders_result = await db.execute(
        select(MaterialFolder)
        .where(MaterialFolder.user_id == current_user.id)
        .order_by(MaterialFolder.created_at.asc())
    )
    available = []
    for folder in folders_result.scalars().all():
        materials_result = await db.execute(
            select(Material).where(Material.folder_id == folder.id)
        )
        materials = materials_result.scalars().all()
        if materials and all(m.status == "indexed" for m in materials):
            available.append({"id": folder.id, "name": folder.name})
    return available


# ---------------- 项目 CRUD ----------------

@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder_result = await db.execute(
        select(MaterialFolder).where(
            MaterialFolder.id == body.folder_id,
            MaterialFolder.user_id == current_user.id,
        )
    )
    if not folder_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="素材库不存在")

    project = Project(name=body.name, user_id=current_user.id, folder_id=body.folder_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.asc())
    )
    return result.scalars().all()


@router.patch("/{project_id}", response_model=ProjectOut)
async def rename_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_owned_project(db, project_id, current_user)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    project.name = name
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_owned_project(db, project_id, current_user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_owned_project(db, project_id, current_user)
    docs_result = await db.execute(
        select(Document).where(
            Document.project_id == project_id, Document.file_key.isnot(None)
        )
    )
    for doc in docs_result.scalars().all():
        storage.remove(doc.file_key)
    await db.delete(project)
    await db.commit()


# ---------------- 素材片段（用于挂载选择）----------------

@router.get("/{project_id}/chunks")
async def list_project_chunks(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_owned_project(db, project_id, current_user)
    rows = await db.execute(
        select(
            MaterialChunk.id,
            MaterialChunk.content,
            MaterialChunk.summary,
            MaterialChunk.chunk_index,
            Material.filename,
        )
        .join(Material, Material.id == MaterialChunk.material_id)
        .where(Material.folder_id == project.folder_id)
        .order_by(Material.filename, MaterialChunk.chunk_index)
    )
    return [
        {
            "chunk_id": r[0],
            "content": r[1],
            "summary": r[2],
            "chunk_index": r[3],
            "file_name": r[4],
        }
        for r in rows.all()
    ]


# ---------------- AI 共创讨论 ----------------

OPENING_GREETING = "你好，今天我们想讨论的主题是什么呢？简单描述一下方向、想表达的观点或你的困惑就好。"


@router.post("/{project_id}/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    project_id: str,
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    # 创建讨论不读素材、不调模型：先给固定开场白，待用户给出方向后再处理
    topic = (body.topic or "").strip()
    conv = Conversation(project_id=project_id, topic=topic, context=None)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    # 每个讨论默认带上 观点 / 案例 / 草稿 三张卡片（空内容、不可删除）
    db.add(DraftCard(project_id=project_id, conversation_id=conv.id, type="viewpoint", content="", is_default=True))
    db.add(DraftCard(project_id=project_id, conversation_id=conv.id, type="case", content="", is_default=True))
    db.add(DraftCard(project_id=project_id, conversation_id=conv.id, type="plan", title="草稿", content="", is_default=True))
    greeting = f"关于「{topic}」，你想从哪些角度展开？说说你的想法、观点或困惑吧。" if topic else OPENING_GREETING
    msg = Message(conversation_id=conv.id, role="assistant", content=greeting)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return {
        "id": conv.id,
        "topic": conv.topic,
        "created_at": conv.created_at,
        "messages": [
            {"id": msg.id, "role": msg.role, "content": msg.content, "created_at": msg.created_at}
        ],
    }


@router.get("/{project_id}/conversations")
async def list_conversations(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    result = await db.execute(
        select(Conversation)
        .where(Conversation.project_id == project_id)
        .order_by(Conversation.created_at.desc())
    )
    return [
        {"id": c.id, "topic": c.topic, "created_at": c.created_at}
        for c in result.scalars().all()
    ]


async def _get_conversation(db, project_id, conv_id) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.project_id == project_id
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


async def _messages(db, conv_id) -> list[Message]:
    result = await db.execute(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    )
    return list(result.scalars().all())


@router.get("/{project_id}/conversations/{conv_id}")
async def get_conversation(
    project_id: str,
    conv_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    conv = await _get_conversation(db, project_id, conv_id)
    msgs = await _messages(db, conv_id)
    return {
        "id": conv.id,
        "topic": conv.topic,
        "created_at": conv.created_at,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in msgs
        ],
    }


@router.delete("/{project_id}/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    project_id: str,
    conv_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    conv = await _get_conversation(db, project_id, conv_id)
    await db.delete(conv)
    await db.commit()


@router.post("/{project_id}/conversations/{conv_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_message(
    project_id: str,
    conv_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_owned_project(db, project_id, current_user)
    conv = await _get_conversation(db, project_id, conv_id)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 首条用户消息即本次讨论主题；此时才构建素材摘要上下文
    if not (conv.topic or "").strip():
        conv.topic = content[:40]
    if not conv.context:
        conv.context = await _build_context(db, project.folder_id)

    db.add(Message(conversation_id=conv_id, role="user", content=content))
    await db.commit()

    msgs = await _messages(db, conv_id)
    history = [{"role": m.role, "content": m.content} for m in msgs]
    answer = await asyncio.to_thread(chat_svc.reply, conv.topic, conv.context or "", history)

    assistant = Message(conversation_id=conv_id, role="assistant", content=answer)
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return {
        "id": assistant.id,
        "role": assistant.role,
        "content": assistant.content,
        "created_at": assistant.created_at,
    }


# ---------------- 草稿卡片 ----------------

@router.get("/{project_id}/cards")
async def list_cards(
    project_id: str,
    conversation_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    query = select(DraftCard).where(DraftCard.project_id == project_id)
    if conversation_id:
        query = query.where(DraftCard.conversation_id == conversation_id)
    result = await db.execute(query.order_by(DraftCard.created_at))
    return [
        {"id": c.id, "type": c.type, "title": c.title, "content": c.content,
         "is_default": bool(c.is_default), "created_at": c.created_at}
        for c in result.scalars().all()
    ]


@router.post("/{project_id}/cards", status_code=status.HTTP_201_CREATED)
async def create_card(
    project_id: str,
    body: CardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    card = DraftCard(
        project_id=project_id,
        conversation_id=body.conversation_id,
        type=body.type or "viewpoint",
        title=body.title,
        content=body.content,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return {"id": card.id, "type": card.type, "title": card.title, "content": card.content,
            "is_default": bool(card.is_default), "created_at": card.created_at}


async def _get_card(db, project_id, card_id) -> DraftCard:
    result = await db.execute(
        select(DraftCard).where(DraftCard.id == card_id, DraftCard.project_id == project_id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return card


@router.patch("/{project_id}/cards/{card_id}")
async def update_card(
    project_id: str,
    card_id: str,
    body: CardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    card = await _get_card(db, project_id, card_id)
    if body.type is not None:
        card.type = body.type
    if body.title is not None:
        card.title = body.title
    if body.content is not None:
        card.content = body.content
    await db.commit()
    await db.refresh(card)
    return {"id": card.id, "type": card.type, "title": card.title, "content": card.content,
            "is_default": bool(card.is_default), "created_at": card.created_at}


@router.delete("/{project_id}/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    project_id: str,
    card_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    card = await _get_card(db, project_id, card_id)
    if card.is_default:
        raise HTTPException(status_code=400, detail="默认卡片不可删除")
    await db.delete(card)
    await db.commit()


# 把观点/案例卡片内容保存进项目绑定的素材库
@router.post("/{project_id}/cards/{card_id}/save-material", status_code=status.HTTP_201_CREATED)
async def save_card_as_material(
    project_id: str,
    card_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_owned_project(db, project_id, current_user)
    card = await _get_card(db, project_id, card_id)
    if card.type not in ("viewpoint", "case"):
        raise HTTPException(status_code=400, detail="仅观点/案例卡片可保存为素材")
    content = (card.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="卡片内容为空，无法保存")

    # 文件名带上讨论名称：讨论名称-观点/案例.md
    topic = "讨论"
    if card.conversation_id:
        conv = await db.get(Conversation, card.conversation_id)
        if conv and (conv.topic or "").strip():
            topic = conv.topic.strip()
    label = "观点" if card.type == "viewpoint" else "案例"
    safe_topic = topic.replace("/", "_").replace("\\", "_")
    filename = f"{safe_topic}-{label}.md"
    object_key = f"{current_user.id}/{project.folder_id}/{filename}"

    # 同名覆盖：删除该素材库下同名旧素材（含其片段、旧文件）
    existing = await db.execute(
        select(Material).where(
            Material.folder_id == project.folder_id, Material.filename == filename
        )
    )
    old = existing.scalar_one_or_none()
    if old:
        storage.remove(old.object_key)
        await db.execute(delete(Material).where(Material.id == old.id))
        await db.commit()

    material = Material(
        folder_id=project.folder_id,
        filename=filename,
        object_key=object_key,
        status="upload_success",
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    storage.put(object_key, content.encode("utf-8"))
    background_tasks.add_task(index_material, material.id)
    return {"id": material.id, "filename": filename, "status": material.status}


# ---------------- 写作方案（基于草稿卡片，生成即保存为一份）----------------

@router.post("/{project_id}/plan")
async def generate_plan(
    project_id: str,
    body: PlanGenerate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_owned_project(db, project_id, current_user)
    result = await db.execute(
        select(DraftCard)
        .where(
            DraftCard.project_id == project_id,
            DraftCard.conversation_id == body.conversation_id,
        )
        .order_by(DraftCard.created_at)
    )
    # 仅用「方案」卡片生成写作方案；观点/案例不发送给大模型
    cards = [
        {"type": c.type, "title": c.title, "content": c.content}
        for c in result.scalars().all()
        if c.type == "plan" and (c.content or "").strip()
    ]
    if not cards:
        raise HTTPException(status_code=400, detail="请先在讨论中填写「方案」卡片内容")
    content = await asyncio.to_thread(authoring.generate_plan, project.name, cards)

    count = await db.execute(
        select(func.count()).select_from(WritingPlan).where(WritingPlan.project_id == project_id)
    )
    name = f"写作方案 {count.scalar() + 1}"
    plan = WritingPlan(project_id=project_id, name=name, content=content)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {"id": plan.id, "name": plan.name, "content": plan.content, "created_at": plan.created_at}


# ---------------- 已保存的写作方案（可多份）----------------

@router.get("/{project_id}/plans")
async def list_plans(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    result = await db.execute(
        select(WritingPlan).where(WritingPlan.project_id == project_id).order_by(WritingPlan.created_at)
    )
    return [
        {"id": p.id, "name": p.name, "content": p.content, "created_at": p.created_at}
        for p in result.scalars().all()
    ]


@router.post("/{project_id}/plans", status_code=status.HTTP_201_CREATED)
async def create_plan_item(
    project_id: str,
    body: PlanItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    name = body.name.strip() or "未命名方案"
    plan = WritingPlan(project_id=project_id, name=name, content=body.content)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {"id": plan.id, "name": plan.name, "content": plan.content, "created_at": plan.created_at}


async def _get_plan_item(db, project_id, plan_id) -> WritingPlan:
    result = await db.execute(
        select(WritingPlan).where(WritingPlan.id == plan_id, WritingPlan.project_id == project_id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="方案不存在")
    return plan


@router.patch("/{project_id}/plans/{plan_id}")
async def update_plan_item(
    project_id: str,
    plan_id: str,
    body: PlanItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    plan = await _get_plan_item(db, project_id, plan_id)
    if body.name is not None:
        plan.name = body.name
    if body.content is not None:
        plan.content = body.content
    await db.commit()
    await db.refresh(plan)
    return {"id": plan.id, "name": plan.name, "content": plan.content, "created_at": plan.created_at}


@router.delete("/{project_id}/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan_item(
    project_id: str,
    plan_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    plan = await _get_plan_item(db, project_id, plan_id)
    await db.delete(plan)
    await db.commit()


# ---------------- 已保存的文章（可多份）----------------

@router.get("/{project_id}/articles")
async def list_articles(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    result = await db.execute(
        select(SavedArticle).where(SavedArticle.project_id == project_id).order_by(SavedArticle.created_at)
    )
    return [
        {"id": a.id, "name": a.name, "content": a.content, "created_at": a.created_at}
        for a in result.scalars().all()
    ]


@router.post("/{project_id}/articles", status_code=status.HTTP_201_CREATED)
async def create_article_item(
    project_id: str,
    body: ArticleItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    name = body.name.strip() or "未命名文章"
    art = SavedArticle(project_id=project_id, name=name, content=body.content)
    db.add(art)
    await db.commit()
    await db.refresh(art)
    return {"id": art.id, "name": art.name, "content": art.content, "created_at": art.created_at}


async def _get_article_item(db, project_id, article_id) -> SavedArticle:
    result = await db.execute(
        select(SavedArticle).where(SavedArticle.id == article_id, SavedArticle.project_id == project_id)
    )
    art = result.scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail="文章不存在")
    return art


@router.patch("/{project_id}/articles/{article_id}")
async def update_article_item(
    project_id: str,
    article_id: str,
    body: ArticleItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    art = await _get_article_item(db, project_id, article_id)
    if body.name is not None:
        art.name = body.name
    if body.content is not None:
        art.content = body.content
    await db.commit()
    await db.refresh(art)
    return {"id": art.id, "name": art.name, "content": art.content, "created_at": art.created_at}


@router.delete("/{project_id}/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article_item(
    project_id: str,
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    art = await _get_article_item(db, project_id, article_id)
    await db.delete(art)
    await db.commit()


# ---------------- 结构树 ----------------

@router.post("/{project_id}/trees", status_code=status.HTTP_201_CREATED)
async def create_tree(
    project_id: str,
    body: TreeGenerate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_owned_project(db, project_id, current_user)
    plan = await _get_plan_item(db, project_id, body.plan_id)
    if not (plan.content or "").strip():
        raise HTTPException(status_code=400, detail="该写作方案内容为空")
    # 结构生成 + 素材筛选挂载较耗时，放后台；立即返回 generating 状态
    tree = Tree(project_id=project_id, name=project.name, nodes={}, status="generating")
    db.add(tree)
    await db.commit()
    await db.refresh(tree)
    background_tasks.add_task(build_tree, tree.id, project_id, plan.content)
    return {"id": tree.id, "name": tree.name, "nodes": tree.nodes, "status": tree.status, "created_at": tree.created_at}


@router.get("/{project_id}/trees")
async def list_trees(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    trees_result = await db.execute(
        select(Tree).where(Tree.project_id == project_id).order_by(Tree.created_at.asc())
    )
    return [
        {"id": t.id, "name": t.name, "nodes": t.nodes, "status": t.status, "created_at": t.created_at}
        for t in trees_result.scalars().all()
    ]


async def _get_tree(db, project_id, tree_id) -> Tree:
    result = await db.execute(
        select(Tree).where(Tree.id == tree_id, Tree.project_id == project_id)
    )
    tree = result.scalar_one_or_none()
    if not tree:
        raise HTTPException(status_code=404, detail="结构树不存在")
    return tree


@router.patch("/{project_id}/trees/{tree_id}")
async def update_tree(
    project_id: str,
    tree_id: str,
    body: TreeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    tree = await _get_tree(db, project_id, tree_id)
    if body.name is not None:
        tree.name = body.name
    if body.nodes is not None:
        tree.nodes = body.nodes
    await db.commit()
    await db.refresh(tree)
    return {"id": tree.id, "name": tree.name, "nodes": tree.nodes, "status": tree.status, "created_at": tree.created_at}


@router.delete("/{project_id}/trees/{tree_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tree(
    project_id: str,
    tree_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    tree = await _get_tree(db, project_id, tree_id)
    await db.delete(tree)
    await db.commit()


# ---------------- 文章生成 ----------------

@router.post("/{project_id}/trees/{tree_id}/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    project_id: str,
    tree_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    await _get_tree(db, project_id, tree_id)

    # 一棵树仅保留一篇文章：再次生成会替换旧文档（含存储文件）
    old = await db.execute(
        select(Document).where(Document.tree_id == tree_id, Document.project_id == project_id)
    )
    for d in old.scalars().all():
        if d.file_key:
            storage.remove(d.file_key)
        await db.delete(d)
    await db.commit()

    doc = Document(project_id=project_id, tree_id=tree_id, status="pending")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(generate_document, doc.id, tree_id, project_id)
    return {"id": doc.id, "status": doc.status, "created_at": doc.created_at}


@router.get("/{project_id}/trees/{tree_id}/documents")
async def list_documents(
    project_id: str,
    tree_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    docs_result = await db.execute(
        select(Document)
        .where(Document.tree_id == tree_id, Document.project_id == project_id)
        .order_by(Document.created_at.desc())
    )
    return [
        {"id": d.id, "status": d.status, "file_key": d.file_key, "created_at": d.created_at}
        for d in docs_result.scalars().all()
    ]


@router.get("/{project_id}/trees/{tree_id}/documents/{document_id}/download")
async def download_document(
    project_id: str,
    tree_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_project(db, project_id, current_user)
    doc_result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tree_id == tree_id,
            Document.project_id == project_id,
        )
    )
    doc = doc_result.scalar_one_or_none()
    if not doc or doc.status != "done" or not doc.file_key:
        raise HTTPException(status_code=404, detail="文档不存在或未生成完成")

    content = storage.get(doc.file_key)
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=document.md"},
    )
