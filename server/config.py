"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    ANTHROPIC_ROUTER_MODEL = os.getenv("ANTHROPIC_ROUTER_MODEL", "claude-haiku-4-5-20251001")
    ANTHROPIC_MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))
    ANTHROPIC_MAX_RETRIES = int(os.getenv("ANTHROPIC_MAX_RETRIES", "3"))

    POSTGRES_USER = os.getenv("POSTGRES_USER", "shop")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "smart_shop")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
    RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.25"))

    MEMORY_MAX_MESSAGES = int(os.getenv("MEMORY_MAX_MESSAGES", "8"))

    @classmethod
    def database_url(cls) -> str:
        return (
            f"postgresql://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}"
            f"@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"
        )

    @classmethod
    def missing_secrets(cls) -> list:
        missing = []
        if not cls.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        if not cls.POSTGRES_PASSWORD:
            missing.append("POSTGRES_PASSWORD")
        return missing
