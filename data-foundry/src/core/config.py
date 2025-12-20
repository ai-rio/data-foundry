"""
Data Foundry Configuration - The "Glue" Layer

This module manages all external service connections and application settings.
It serves as the central configuration hub for the entire platform.
"""

from pydantic_settings import BaseSettings
from typing import Optional, List
import os
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    This is the single source of truth for all configuration.
    """

    # Application Settings
    APP_NAME: str = "Data Foundry"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-change-in-production"

    # API Settings
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Database Configuration
    DATABASE_URL: str = "postgresql://foundry_user:foundry_password@localhost:5432/data_foundry"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TASK_QUEUE_NAME: str = "data_foundry_tasks"

    # AI Model Configuration
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.3
    OPENAI_MAX_TOKENS: int = 2048

    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-opus-20240229"
    ANTHROPIC_TEMPERATURE: float = 0.3
    ANTHROPIC_MAX_TOKENS: int = 2048

    # Label Studio Configuration
    LABEL_STUDIO_URL: str = "http://localhost:8080"
    LABEL_STUDIO_API_KEY: Optional[str] = None
    LABEL_STUDIO_PROJECT_ID: int = 1

    # Stripe Configuration
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_AI_LABEL_METER_ID: Optional[str] = None
    STRIPE_HUMAN_AUDIT_METER_ID: Optional[str] = None

    # Security Settings
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # File Upload Settings
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_FILE_TYPES: List[str] = ["csv", "json", "xlsx", "parquet"]

    # Task Configuration
    TASK_TIMEOUT_SECONDS: int = 3600  # 1 hour
    MAX_CONCURRENT_TASKS: int = 10

    # Data Processing Configuration
    DEFAULT_BATCH_SIZE: int = 1000
    MAX_BATCH_SIZE: int = 10000

    # Privacy and Compliance
    ENABLE_PII_REDACTION: bool = True
    CONFIDENCE_THRESHOLD: float = 0.85  # Below this triggers human review

    # Monitoring and Logging
    LOG_LEVEL: str = "INFO"
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL."""
        if self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        return self.DATABASE_URL

    @property
    def database_url_async(self) -> str:
        """Get asynchronous database URL."""
        if not self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
        return self.DATABASE_URL


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    This ensures settings are loaded only once.
    """
    return Settings()


# Export the settings instance
settings = get_settings()


# Connection strings for external services (the "glue")
EXTERNAL_SERVICES = {
    "postgres": settings.DATABASE_URL,
    "redis": settings.REDIS_URL,
    "label_studio": f"{settings.LABEL_STUDIO_URL}/api",
    "prefect": "http://localhost:4200/api",
}

# AI Provider configurations
AI_PROVIDERS = {
    "openai": {
        "api_key": settings.OPENAI_API_KEY,
        "model": settings.OPENAI_MODEL,
        "temperature": settings.OPENAI_TEMPERATURE,
        "max_tokens": settings.OPENAI_MAX_TOKENS,
    },
    "anthropic": {
        "api_key": settings.ANTHROPIC_API_KEY,
        "model": settings.ANTHROPIC_MODEL,
        "temperature": settings.ANTHROPIC_TEMPERATURE,
        "max_tokens": settings.ANTHROPIC_MAX_TOKENS,
    }
}