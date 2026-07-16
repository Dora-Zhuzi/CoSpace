import uuid
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    BackgroundTasks,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.storage import storage, safe_filename
from app.models.user import User
from app.models.project import Project
from app.models.material import MaterialFolder, Material
from app.schemas.material import FolderCreate, FolderUpdate, FolderOut, FolderDetail, MaterialOut
from app.services.indexer import index_material

router = APIRouter()


# 创建文件夹
@router.post("/folders", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = MaterialFolder(name=body.name, user_id=current_user.id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


# 获取文件夹列表
@router.get("/folders", response_model=list[FolderOut])
async def list_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MaterialFolder)
        .where(MaterialFolder.user_id == current_user.id)
        .order_by(MaterialFolder.created_at.asc())
    )
    return result.scalars().all()


async def _folder_detail(db: AsyncSession, folder: MaterialFolder) -> FolderDetail:
    materials_result = await db.execute(
        select(Material)
        .where(Material.folder_id == folder.id)
        .order_by(Material.created_at.asc())
    )
    materials = materials_result.scalars().all()
    return FolderDetail(
        id=folder.id,
        name=folder.name,
        created_at=folder.created_at,
        materials=[MaterialOut.model_validate(m) for m in materials],
    )


async def _get_owned_folder(db, folder_id, user) -> MaterialFolder:
    result = await db.execute(
        select(MaterialFolder).where(
            MaterialFolder.id == folder_id,
            MaterialFolder.user_id == user.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return folder


# 重命名文件夹
@router.patch("/folders/{folder_id}", response_model=FolderOut)
async def rename_folder(
    folder_id: str,
    body: FolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = await _get_owned_folder(db, folder_id, current_user)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    folder.name = name
    await db.commit()
    await db.refresh(folder)
    return folder


# 删除文件夹（连带其中所有文件）
@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_folder(db, folder_id, current_user)

    # 被项目占用时禁止删除
    used = await db.execute(
        select(Project.id).where(Project.folder_id == folder_id).limit(1)
    )
    if used.first():
        raise HTTPException(status_code=400, detail="该素材库正被项目使用，请先删除相关项目")

    # 清理存储中的文件
    keys = await db.execute(
        select(Material.object_key).where(Material.folder_id == folder_id)
    )
    for (key,) in keys.all():
        storage.remove(key)

    # 删除文件（chunks 经 DB 级 ON DELETE CASCADE 一并清理），再删文件夹
    await db.execute(delete(Material).where(Material.folder_id == folder_id))
    await db.execute(delete(MaterialFolder).where(MaterialFolder.id == folder_id))
    await db.commit()


# 获取文件夹详情（含文件列表）
@router.get("/folders/{folder_id}", response_model=FolderDetail)
async def get_folder(
    folder_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = await _get_owned_folder(db, folder_id, current_user)
    return await _folder_detail(db, folder)


# 上传文件
@router.post("/folders/{folder_id}/upload", response_model=FolderDetail)
async def upload_file(
    folder_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = await _get_owned_folder(db, folder_id, current_user)

    fname = safe_filename(file.filename)
    object_key = f"{current_user.id}/{folder_id}/{uuid.uuid4()}_{fname}"
    material = Material(
        folder_id=folder_id, filename=fname, object_key=object_key, status="uploading"
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    try:
        data = await file.read()
        storage.put(object_key, data)
        material.status = "upload_success"
        await db.commit()
        background_tasks.add_task(index_material, material.id)
    except Exception as e:
        material.status = "upload_failed"
        material.error = str(e)[:500]
        await db.commit()

    return await _folder_detail(db, folder)


# 删除文件
@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Material)
        .join(MaterialFolder)
        .where(Material.id == material_id, MaterialFolder.user_id == current_user.id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="文件不存在")

    if material.status in ("uploading", "indexing"):
        raise HTTPException(status_code=400, detail="处理中的文件不能删除")

    storage.remove(material.object_key)
    await db.delete(material)
    await db.commit()
