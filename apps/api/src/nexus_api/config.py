from typing import List, AsyncGenerator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import redis.asyncio as aioredis
import logging

logger = logging.getLogger("nexus-config")

Base = declarative_base()


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
    redis_event_stream: str = "nexus:events:stream"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

# Async PostgreSQL Engine & Session Pool
engine = create_async_engine(
    settings.postgres_dsn,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Async Redis Connection Pool
redis_pool: aioredis.Redis = aioredis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True
)


async def get_redis_client() -> aioredis.Redis:
    return redis_pool
