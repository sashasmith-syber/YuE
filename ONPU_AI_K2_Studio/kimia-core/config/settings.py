"""
ONPU K2 Studio - Configuration Settings
Pydantic Settings with environment variable support
"""

import os
from typing import List, Optional
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator


class Settings(BaseSettings):
    """
    Application settings with environment variable validation.
    Zero hardcoded secrets - env only.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )
    
    # Application
    APP_NAME: str = "ONPU AI K2 Studio"
    APP_VERSION: str = "4.0.0"
    DEBUG: bool = Field(default=False, description="Debug mode")
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    
    # Security
    JWT_SECRET_KEY: str = Field(
        default="",
        description="JWT signing secret - MUST be set in production"
    )
    KAIZEN_SHA_WHITELIST: List[str] = Field(
        default=[],
        description="List of allowed device fingerprints"
    )
    ADMIN_SECRET: str = Field(
        default="",
        description="Admin API key for sensitive operations"
    )
    
    # Kimi-Audio Model
    KIMIA_MODEL_PATH: str = Field(
        default="moonshotai/Kimi-Audio-7B-Instruct",
        description="HuggingFace model path or local cache"
    )
    KIMIA_DEVICE: str = Field(
        default="cuda:0",
        description="Device for model inference (cuda:0 or cpu)"
    )
    KIMIA_LOAD_DETOKENIZER: bool = Field(
        default=True,
        description="Load audio detokenizer for generation"
    )
    KIMIA_MAX_LENGTH: int = Field(
        default=2048,
        description="Maximum generation length"
    )
    KIMIA_TEMPERATURE: float = Field(
        default=0.7,
        description="Generation temperature"
    )
    
    # GPU Memory Management
    KIMIA_GPU_IDLE_TIMEOUT: int = Field(
        default=300,
        description="Seconds before unloading model from GPU"
    )
    KIMIA_GPU_MEMORY_FRACTION: float = Field(
        default=0.8,
        description="Fraction of GPU memory to use"
    )
    
    # Database - TimescaleDB
    TIMESCALEDB_URL: str = Field(
        default="",
        description="TimescaleDB connection string"
    )
    TIMESCALEDB_POOL_SIZE: int = Field(default=10)
    TIMESCALEDB_MAX_OVERFLOW: int = Field(default=20)
    
    # Database - ClickHouse (Logs)
    CLICKHOUSE_URL: str = Field(
        default="",
        description="ClickHouse connection string"
    )
    CLICKHOUSE_DATABASE: str = Field(default="onpu_logs")
    
    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string"
    )
    
    # Celery
    CELERY_BROKER_URL: str = Field(default="")
    CELERY_RESULT_BACKEND: str = Field(default="")
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=1000)
    RATE_LIMIT_FAILED_AUTH_THRESHOLD: int = Field(
        default=3,
        description="Failed auth attempts per minute before IP block"
    )
    RATE_LIMIT_IP_BLOCK_DURATION_MINUTES: int = Field(default=30)
    
    # Security
    SECURITY_STRICT_MODE: bool = Field(
        default=False,
        description="Enable strict validation mode (blocks on any violation)"
    )
    SECURITY_BPM_MIN: float = Field(default=60.0)
    SECURITY_BPM_MAX: float = Field(default=200.0)
    SECURITY_ANOMALY_BLOCK_THRESHOLD: float = Field(default=0.9)
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )
    
    # Monitoring
    PROMETHEUS_PORT: int = Field(default=9090)
    GRAFANA_PORT: int = Field(default=3000)
    
    # Triton Inference Server
    TRITON_URL: str = Field(
        default="",
        description="Triton Inference Server URL"
    )
    TRITON_MODEL_NAME: str = Field(default="kimi-audio")
    
    # SSmith25 Sonic Parameters
    SONIC_TARGET_BPM: float = Field(default=122.0)
    SONIC_BPM_TOLERANCE: float = Field(default=3.0)
    SONIC_ALLOWED_KEYS: List[str] = Field(
        default=["C# minor", "D minor", "F# minor"]
    )
    SONIC_TARGET_SUB_FREQ: float = Field(default=38.9)
    SONIC_SUB_FREQ_TOLERANCE: float = Field(default=3.1)
    SONIC_TARGET_LUFS: float = Field(default=-8.2)
    SONIC_LUFS_TOLERANCE: float = Field(default=2.0)
    SONIC_TARGET_DR: float = Field(default=7.0)
    
    @validator("KAIZEN_SHA_WHITELIST", pre=True)
    def parse_kaizen_whitelist(cls, v):
        """Parse comma-separated fingerprints."""
        if isinstance(v, str):
            return [f.strip() for f in v.split(",") if f.strip()]
        return v
    
    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_allowed_origins(cls, v):
        """Parse comma-separated origins."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v
    
    @validator("CELERY_BROKER_URL", pre=True)
    def set_celery_broker(cls, v, values):
        """Default to REDIS_URL if not set."""
        if not v:
            return values.data.get("REDIS_URL", "redis://localhost:6379/0")
        return v
    
    @validator("CELERY_RESULT_BACKEND", pre=True)
    def set_celery_backend(cls, v, values):
        """Default to REDIS_URL if not set."""
        if not v:
            return values.data.get("REDIS_URL", "redis://localhost:6379/0")
        return v
    
    @validator("JWT_SECRET_KEY")
    def validate_jwt_secret(cls, v):
        """Warn if using default JWT secret."""
        if not v or len(v) < 32:
            import warnings
            warnings.warn(
                "JWT_SECRET_KEY is not set or too short. "
                "Set a secure secret in production!",
                RuntimeWarning
            )
        return v
    
    @validator("ADMIN_SECRET")
    def validate_admin_secret(cls, v):
        """Warn if using default admin secret."""
        if not v:
            import warnings
            warnings.warn(
                "ADMIN_SECRET is not set. "
                "Admin operations will fail!",
                RuntimeWarning
            )
        return v


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
