"""
Configuration settings for Agentic Stack.

Loads configuration from environment variables and YAML files.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RedisConfig:
    """Redis connection configuration."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None

    @property
    def url(self) -> str:
        """Get Redis connection URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class RabbitMQConfig:
    """RabbitMQ connection configuration."""

    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    vhost: str = "/"

    @property
    def url(self) -> str:
        """Get RabbitMQ connection URL."""
        return f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/{self.vhost}"


@dataclass
class VaultConfig:
    """HashiCorp Vault configuration."""

    address: str = "http://localhost:8200"
    token: str | None = None
    namespace: str | None = None


@dataclass
class LLMConfig:
    """LLM (Claude API) configuration."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str | None = None
    max_tokens: int = 16000
    temperature: float = 0.7


@dataclass
class Settings:
    """Main settings class for Agentic Stack."""

    # Environment
    environment: str = "development"
    debug: bool = True

    # Project paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)

    # Service configurations
    redis: RedisConfig = field(default_factory=RedisConfig)
    rabbitmq: RabbitMQConfig = field(default_factory=RabbitMQConfig)
    vault: VaultConfig = field(default_factory=VaultConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Agent settings
    max_concurrent_tasks: int = 10
    task_timeout_seconds: int = 3600
    heartbeat_interval_seconds: int = 30

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        settings = cls()

        # Environment
        settings.environment = os.getenv("AGENTIC_ENV", "development")
        settings.debug = os.getenv("AGENTIC_DEBUG", "true").lower() == "true"

        # Redis
        settings.redis.host = os.getenv("REDIS_HOST", "localhost")
        settings.redis.port = int(os.getenv("REDIS_PORT", "6379"))
        settings.redis.password = os.getenv("REDIS_PASSWORD")

        # RabbitMQ
        settings.rabbitmq.host = os.getenv("RABBITMQ_HOST", "localhost")
        settings.rabbitmq.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        settings.rabbitmq.username = os.getenv("RABBITMQ_USERNAME", "guest")
        settings.rabbitmq.password = os.getenv("RABBITMQ_PASSWORD", "guest")

        # Vault
        settings.vault.address = os.getenv("VAULT_ADDR", "http://localhost:8200")
        settings.vault.token = os.getenv("VAULT_TOKEN")

        # LLM
        settings.llm.api_key = os.getenv("ANTHROPIC_API_KEY")
        settings.llm.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        # Logging
        settings.log_level = os.getenv("LOG_LEVEL", "INFO")

        return settings

    @classmethod
    def from_yaml(cls, config_path: Path) -> "Settings":
        """Load settings from a YAML file."""
        settings = cls.from_env()

        if config_path.exists():
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}

            # Apply YAML overrides
            if "redis" in config:
                for key, value in config["redis"].items():
                    if hasattr(settings.redis, key):
                        setattr(settings.redis, key, value)

            if "rabbitmq" in config:
                for key, value in config["rabbitmq"].items():
                    if hasattr(settings.rabbitmq, key):
                        setattr(settings.rabbitmq, key, value)

            if "vault" in config:
                for key, value in config["vault"].items():
                    if hasattr(settings.vault, key):
                        setattr(settings.vault, key, value)

            if "llm" in config:
                for key, value in config["llm"].items():
                    if hasattr(settings.llm, key):
                        setattr(settings.llm, key, value)

        return settings

    @property
    def ai_dir(self) -> Path:
        """Get the .ai directory path."""
        return self.project_root / ".ai"

    @property
    def memory_dir(self) -> Path:
        """Get the memory directory path."""
        return self.ai_dir / "memory"

    @property
    def metrics_dir(self) -> Path:
        """Get the metrics directory path."""
        return self.ai_dir / "metrics"

    @property
    def logs_dir(self) -> Path:
        """Get the logs directory path."""
        return self.project_root / "logs"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_env()


def load_settings(config_path: Path | None = None) -> Settings:
    """
    Load settings from YAML file and clear cache.

    Args:
        config_path: Path to YAML config file (optional)

    Returns:
        Settings instance
    """
    get_settings.cache_clear()
    if config_path:
        return Settings.from_yaml(config_path)
    return Settings.from_env()
