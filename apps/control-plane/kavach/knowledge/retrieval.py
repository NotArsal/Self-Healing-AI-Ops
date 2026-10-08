from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from kavach.api.models import IncidentMemory
from kavach.knowledge.embeddings import generate_embedding
import logging

logger = logging.getLogger(__name__)

async def retrieve_similar_incidents(
    session: AsyncSession,
    query_text: str,
    limit: int = 3
) -> list[IncidentMemory]:
    """Retrieves past incidents similar to the query text."""
    query_embedding = await generate_embedding(query_text)
    
    if not query_embedding:
        logger.warning("Could not generate query embedding. Returning empty evidence.")
        return []

    try:
        stmt = (
            select(IncidentMemory)
            .where(IncidentMemory.embedding.is_not(None))
            .order_by(IncidentMemory.embedding.l2_distance(query_embedding))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    except Exception as e:
        logger.error(f"Failed to retrieve similar incidents: {e}")
        return []
