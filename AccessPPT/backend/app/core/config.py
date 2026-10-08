import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DB_FILE = (BACKEND_DIR / "accessppt.db").resolve()
ENV_FILE = BACKEND_DIR / ".env"
ROOT_ENV_FILE = BACKEND_DIR.parent / ".env"


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AccessPPT"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    SECRET_KEY: str = "change-this-secret-key-in-production"

    # Database: Default to local SQLite with absolute path for zero-config execution
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DB_FILE.as_posix()}"
    DATABASE_SYNC_URL: str = f"sqlite:///{DB_FILE.as_posix()}"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-pro"

    # S3 Storage
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "accessppt"
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False

    # JWT
    JWT_SECRET: str = "change-this-secret-key-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 10080  # 7 days

    # File Upload
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: str = "pptx"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def resolve_sqlite_url(cls, v):
        if isinstance(v, str) and (v.startswith("sqlite+aiosqlite:///.") or v == "sqlite+aiosqlite:///./accessppt.db"):
            return f"sqlite+aiosqlite:///{DB_FILE.as_posix()}"
        return v

    @field_validator("DATABASE_SYNC_URL", mode="before")
    @classmethod
    def resolve_sync_sqlite_url(cls, v):
        if isinstance(v, str) and (v.startswith("sqlite:///.") or v == "sqlite:///./accessppt.db"):
            return f"sqlite:///{DB_FILE.as_posix()}"
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    model_config = {
        "env_file": str(ENV_FILE) if ENV_FILE.exists() else (str(ROOT_ENV_FILE) if ROOT_ENV_FILE.exists() else ".env"),
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()
