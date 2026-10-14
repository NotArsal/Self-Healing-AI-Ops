import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Must match infra/docker-compose.yml. The previous default used password
# "postgres" against a container created with "password", so every write in the
# debt and knowledge paths failed authentication and was swallowed by the bare
# excepts around them. Override with DATABASE_URL; see .env.example.
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5433/kavach"
)

# NullPool, deliberately. Several callers reach the database from inside a sync
# graph node via asyncio.run(), which builds and tears down an event loop per
# call. A pooled asyncpg connection is bound to the loop that created it, so the
# next call inherits a connection whose loop is closed and blocks forever. This
# surfaced the moment the credentials above started working: the knowledge-base
# read pooled a connection and the write after it deadlocked.
#
# The real fix is for graph nodes not to open event loops at all -- see the
# asyncio.run() calls in graph/nodes.py. Until those are restructured, not
# pooling is what keeps the loop from hanging, and the cost is one connect per
# incident.
engine = create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
