import os
import shutil
from pathlib import Path
from app.core.config import settings


class LocalStorage:
    """本地文件系统对象存储，替代 MinIO。key 形如 'user/folder/uuid_name.pdf'。"""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # 防止路径穿越：规范化后必须仍在 root 内
        target = (self.root / key).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise ValueError("非法的存储 key")
        return target

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def remove(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


storage = LocalStorage(settings.storage_dir)


def safe_filename(name: str) -> str:
    """只保留文件名部分，去掉任何目录成分。"""
    return os.path.basename(name or "file").strip() or "file"


# 兼容旧代码用法的别名
def get_storage() -> LocalStorage:
    return storage
