from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NEXUS API"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    allowed_origins: List[str] = ["*"]
    
    # Storage and queues
    postgres_dsn: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_db"
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
