from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- 存储 ----
    # 默认 SQLite，文件落在 backend/docgen.db；可改为 postgresql+asyncpg://...
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'docgen.db'}"
    # 本地对象存储根目录（替代 MinIO）
    storage_dir: str = str(BASE_DIR / "storage")

    # ---- 鉴权 ----
    jwt_secret: str = "dev-secret-change-me-in-prod"
    jwt_expire_days: int = 7

    # ---- CORS ----
    cors_origins: list[str] = ["http://localhost:3000"]

    # ---- 大模型（OpenAI 兼容接口）----
    # llm_api_key 为空时自动降级到本地实现，保证零配置也能跑通流程。
    # 接 DeepSeek: base_url=https://api.deepseek.com  model=deepseek-chat
    # 接火山方舟 Ark: base_url=<ark_base_url>  model=<endpoint_id>
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # ---- 向量化 ----
    # 优先尝试 sentence-transformers 加载该模型；失败则降级为本地哈希向量。
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 256  # 哈希降级时的维度

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
