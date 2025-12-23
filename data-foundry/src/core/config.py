"""
Data Foundry Configuration - The "Glue" Layer

This module manages all external service connections and application settings.
It serves as the central configuration hub for the entire platform.

SECURITY INTEGRATION: Now uses SecretManager for secure secret management
"""

from functools import lru_cache
import os
import logging

from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field, field_validator
from src.core.secret_manager import SecretManager


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    This is the single source of truth for all configuration.

    SECURITY INTEGRATION: Uses SecretManager for secure secret retrieval
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize SecretManager for secure secret management
        self._secret_manager = SecretManager()
        # Load and encrypt environment secrets on initialization
        self._load_secrets_securely()
        logger.info("Settings initialized with SecretManager integration")

    def _load_secrets_securely(self):
        """Load and encrypt secrets from environment using SecretManager."""
        try:
            # Load and encrypt existing secrets
            encrypted_secrets = self._secret_manager.load_environment_secrets()
            logger.info(f"Securely loaded {len(encrypted_secrets)} encrypted secrets")
        except Exception as e:
            logger.error(f"Failed to load secrets securely: {e}")

    # Application Settings
    APP_NAME: str = "Data Foundry"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str | None = Field(default=None)

    # API Settings
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Database Configuration
    DATABASE_URL: str | None = Field(
        default=None,
        description="PostgreSQL database connection string"
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TASK_QUEUE_NAME: str = "data_foundry_tasks"
    REDIS_CACHE_DB: int = 0
    REDIS_CACHE_PREFIX: str = "data_foundry"
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_RETRY_ATTEMPTS: int = 3
    REDIS_RETRY_DELAY: float = 0.1
    REDIS_HEALTH_CHECK_INTERVAL: float = 30.0
    REDIS_CONNECTION_TIMEOUT: int = 5
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5

    # AI Model Configuration
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.3
    OPENAI_MAX_TOKENS: int = 2048

    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-opus-20240229"
    ANTHROPIC_TEMPERATURE: float = 0.3
    ANTHROPIC_MAX_TOKENS: int = 2048

    # OpenRouter Configuration
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openrouter/openai/gpt-4o-mini"

    # SECURE PROPERTIES: Get secrets through SecretManager
    @property
    def secure_openai_api_key(self) -> str | None:
        """Get OpenAI API key securely through SecretManager."""
        return self._secret_manager.get_secret("OPENAI_API_KEY")

    @property
    def secure_openrouter_api_key(self) -> str | None:
        """Get OpenRouter API key securely through SecretManager."""
        return self._secret_manager.get_secret("OPENROUTER_API_KEY")

    @property
    def secure_anthropic_api_key(self) -> str | None:
        """Get Anthropic API key securely through SecretManager."""
        return self._secret_manager.get_secret("ANTHROPIC_API_KEY")

    @property
    def secure_github_token(self) -> str | None:
        """Get GitHub token securely through SecretManager."""
        return self._secret_manager.get_secret("GITHUB_TOKEN")

    @property
    def secure_label_studio_api_key(self) -> str | None:
        """Get Label Studio API key securely through SecretManager."""
        return self._secret_manager.get_secret("LABEL_STUDIO_API_KEY")

    @property
    def secure_stripe_secret_key(self) -> str | None:
        """Get Stripe secret key securely through SecretManager."""
        return self._secret_manager.get_secret("STRIPE_SECRET_KEY")

    @property
    def secure_database_url(self) -> str:
        """Get database URL securely through SecretManager."""
        encrypted_url = os.getenv("DATABASE_URL_ENCRYPTED")
        if encrypted_url:
            try:
                from src.core.database_security import SecureDatabaseConfig
                db_config = SecureDatabaseConfig()
                return db_config.decrypt_connection_string(encrypted_url)
            except Exception as e:
                logger.error(f"Failed to decrypt database URL: {e}")

        # Fallback to plaintext (with warning)
        url = self.DATABASE_URL
        if url and "password" in url.lower():
            logger.warning("Using plaintext database URL - security risk")
        return url

    @property
    def secure_redis_url(self) -> str:
        """Get Redis URL securely through SecretManager."""
        encrypted_url = os.getenv("REDIS_URL_ENCRYPTED")
        if encrypted_url:
            try:
                from src.core.database_security import SecureDatabaseConfig
                db_config = SecureDatabaseConfig()
                return db_config.decrypt_connection_string(encrypted_url)
            except Exception as e:
                logger.error(f"Failed to decrypt Redis URL: {e}")

        return self.REDIS_URL

    def mask_sensitive_config(self, config_dict: dict) -> dict:
        """Mask sensitive configuration values for logging."""
        return {
            **config_dict,
            "OPENAI_API_KEY": "***" if config_dict.get("OPENAI_API_KEY") else None,
            "OPENROUTER_API_KEY": "***" if config_dict.get("OPENROUTER_API_KEY") else None,
            "ANTHROPIC_API_KEY": "***" if config_dict.get("ANTHROPIC_API_KEY") else None,
            "GITHUB_TOKEN": "***" if config_dict.get("GITHUB_TOKEN") else None,
            "DATABASE_URL": self._secret_manager.mask_secrets_in_log(config_dict.get("DATABASE_URL", "")),
        }

    # LiteLLM Configuration
    LITELLM_LOGGING: bool = True
    LITELLM_CACHE_TTL: int = 3600  # 1 hour
    LITELLM_REQUEST_TIMEOUT: int = 30
    PRIMARY_MODEL: str = "openrouter/openai/gpt-4o-mini"
    FALLBACK_MODELS: list[str] = ["openrouter/anthropic/claude-3.5-sonnet", "openrouter/openai/gpt-4o"]
    MODEL_LIST: list[str] = [
        "openrouter/openai/gpt-4o-mini",
        "openrouter/anthropic/claude-3.5-sonnet",
        "openrouter/openai/gpt-4o",
        "openrouter/openai/gpt-3.5-turbo"
    ]

    # Cost Tracking Configuration
    ENABLE_COST_TRACKING: bool = True
    COST_TRACKING_CURRENCY: str = "USD"
    BILLING_PRECISION: int = 6

    # Label Studio Configuration
    LABEL_STUDIO_URL: str = "http://localhost:8080"
    LABEL_STUDIO_API_KEY: str | None = None
    LABEL_STUDIO_PROJECT_ID: int = 1

    # Stripe Configuration
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_PUBLISHABLE_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_AI_LABEL_METER_ID: str | None = None
    STRIPE_HUMAN_AUDIT_METER_ID: str | None = None

    # Security Settings
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # File Upload Settings
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_FILE_TYPES: list[str] = ["csv", "json", "xlsx", "parquet"]

    # Task Configuration
    TASK_TIMEOUT_SECONDS: int = 3600  # 1 hour
    MAX_CONCURRENT_TASKS: int = 10

    # Data Processing Configuration
    DEFAULT_BATCH_SIZE: int = 1000
    MAX_BATCH_SIZE: int = 10000

    # Privacy and Compliance
    ENABLE_PII_REDACTION: bool = True
    CONFIDENCE_THRESHOLD: float = 0.85  # Below this triggers human review

    # Data Validation Configuration (Week 1: Data Validation + Database Optimization)
    ENABLE_DATA_VALIDATION: bool = True
    MIN_QUALITY_SCORE: float = 0.5
    STAGING_DIRECTORY: str = "data_foundry_staging"

    # A/B Testing Configuration (Week 2: A/B Testing Framework)
    ENABLE_AB_TESTING: bool = False
    AB_TEST_RATIO: float = 0.5  # 50% to treatment
    AB_TEST_NAME: str = "validation_strategy_v1"

    # Monitoring and Logging
    LOG_LEVEL: str = "INFO"
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090

    # Prompt Management Configuration
    PROMPT_TEMPLATE_DIR: str = "src/core/prompts/templates"
    PROMPT_CACHE_ENABLED: bool = True
    PROMPT_CACHE_TTL: int = 3600  # 1 hour
    PROMPT_CACHE_KEY_PREFIX: str = "prompt_cache"
    PROMPT_CACHE_MAX_SIZE: int = 10000
    PROMPT_CACHE_LOCAL_FALLBACK: bool = True
    PROMPT_CACHE_STATS_ENABLED: bool = True
    PROMPT_VERSION_CHECK: bool = True
    PROMPT_VALIDATION_ENABLED: bool = True
    PROMPT_DEBUG_MODE: bool = False

    # Prompt Optimization
    PROMPT_MAX_LENGTH: int = 32000  # Maximum prompt length in characters
    PROMPT_TRUNCATE_ENABLED: bool = False  # Whether to truncate long prompts
    PROMPT_COST_TRACKING: bool = True

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str | None, info) -> str:
        """Validate SECRET_KEY is set in production environments."""
        if v is None:
            # Allow development mode without SECRET_KEY
            if info.data.get("ENVIRONMENT", "development") != "production":
                return "dev-secret-key-for-testing-only"
            raise ValueError(
                "SECRET_KEY must be set via environment variable in production"
            )
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str | None, info) -> str:
        """Validate DATABASE_URL is set."""
        if v is None:
            # For development, provide a default localhost connection
            if info.data.get("ENVIRONMENT", "development") != "production":
                return "postgresql://foundry_user:foundry_password@localhost:5432/data_foundry"
            raise ValueError(
                "DATABASE_URL must be set via environment variable in production"
            )
        return v

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL."""
        if self.DATABASE_URL is None:
            raise ValueError("DATABASE_URL is not set")
        if self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        return self.DATABASE_URL

    @property
    def database_url_async(self) -> str:
        """Get asynchronous database URL."""
        if self.DATABASE_URL is None:
            raise ValueError("DATABASE_URL is not set")
        if not self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
        return self.DATABASE_URL

    @property
    def prompt_template_dir_path(self) -> str:
        """Get absolute path for prompt template directory."""
        import os
        if os.path.isabs(self.PROMPT_TEMPLATE_DIR):
            return self.PROMPT_TEMPLATE_DIR

        # Relative to project root
        return os.path.join(os.getcwd(), self.PROMPT_TEMPLATE_DIR)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    This ensures settings are loaded only once.
    """
    return Settings()


# Export the settings instance
settings = get_settings()


# Connection strings for external services (SECURE - using SecretManager)
EXTERNAL_SERVICES = {
    "postgres": settings.secure_database_url,
    "redis": settings.secure_redis_url,
    "label_studio": f"{settings.LABEL_STUDIO_URL}/api",
    "prefect": "http://localhost:4200/api",
}

# AI Provider configurations (SECURE - using SecretManager)
AI_PROVIDERS = {
    "openai": {
        "api_key": settings.secure_openai_api_key,
        "model": settings.OPENAI_MODEL,
        "temperature": settings.OPENAI_TEMPERATURE,
        "max_tokens": settings.OPENAI_MAX_TOKENS,
    },
    "anthropic": {
        "api_key": settings.secure_anthropic_api_key,
        "model": settings.ANTHROPIC_MODEL,
        "temperature": settings.ANTHROPIC_TEMPERATURE,
        "max_tokens": settings.ANTHROPIC_MAX_TOKENS,
    },
    "openrouter": {
        "api_key": settings.secure_openrouter_api_key,
        "base_url": settings.OPENROUTER_BASE_URL,
        "model": settings.OPENROUTER_MODEL,
    },
    "litellm": {
        "primary_model": settings.PRIMARY_MODEL,
        "fallback_models": settings.FALLBACK_MODELS,
        "model_list": settings.MODEL_LIST,
        "logging": settings.LITELLM_LOGGING,
        "cache_ttl": settings.LITELLM_CACHE_TTL,
        "request_timeout": settings.LITELLM_REQUEST_TIMEOUT,
        "enable_cost_tracking": settings.ENABLE_COST_TRACKING,
        "billing_precision": settings.BILLING_PRECISION,
    },
}

# Prompt Management Configuration
PROMPT_CONFIG = {
    "template_dir": settings.prompt_template_dir_path,
    "cache_enabled": settings.PROMPT_CACHE_ENABLED,
    "cache_ttl": settings.PROMPT_CACHE_TTL,
    "cache_key_prefix": settings.PROMPT_CACHE_KEY_PREFIX,
    "cache_max_size": settings.PROMPT_CACHE_MAX_SIZE,
    "cache_local_fallback": settings.PROMPT_CACHE_LOCAL_FALLBACK,
    "cache_stats_enabled": settings.PROMPT_CACHE_STATS_ENABLED,
    "version_check": settings.PROMPT_VERSION_CHECK,
    "validation_enabled": settings.PROMPT_VALIDATION_ENABLED,
    "debug_mode": settings.PROMPT_DEBUG_MODE,
    "max_length": settings.PROMPT_MAX_LENGTH,
    "truncate_enabled": settings.PROMPT_TRUNCATE_ENABLED,
    "cost_tracking": settings.PROMPT_COST_TRACKING,
}

# Redis Cache Configuration
REDIS_CACHE_CONFIG = {
    "url": settings.REDIS_URL,
    "db": settings.REDIS_CACHE_DB,
    "prefix": settings.REDIS_CACHE_PREFIX,
    "max_connections": settings.REDIS_MAX_CONNECTIONS,
    "retry_attempts": settings.REDIS_RETRY_ATTEMPTS,
    "retry_delay": settings.REDIS_RETRY_DELAY,
    "health_check_interval": settings.REDIS_HEALTH_CHECK_INTERVAL,
    "connection_timeout": settings.REDIS_CONNECTION_TIMEOUT,
    "socket_timeout": settings.REDIS_SOCKET_TIMEOUT,
    "socket_connect_timeout": settings.REDIS_SOCKET_CONNECT_TIMEOUT,
}
