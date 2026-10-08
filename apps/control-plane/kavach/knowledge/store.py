from sqlalchemy.ext.asyncio import AsyncSession
from kavach.api.models import IncidentMemory
from kavach.knowledge.embeddings import generate_embedding
import logging

logger = logging.getLogger(__name__)

async def save_incident_memory(
    session: AsyncSession,
    incident_id: str,
    fault_class: str,
    symptoms: str,
    summary: str,
    repair_action: dict,
    outcome: str
) -> IncidentMemory | None:
    """Embeds the incident context and saves it to the knowledge base."""
    text_to_embed = f"Fault: {fault_class}\nSymptoms: {symptoms}\nSummary: {summary}\nRepair: {repair_action}"
    
    embedding = await generate_embedding(text_to_embed)
    if not embedding:
        logger.warning(f"Failed to generate embedding for incident {incident_id}. Saving without vector.")

    memory = IncidentMemory(
        id=incident_id,
        fault_class=fault_class,
        symptoms=symptoms,
        summary=summary,
        repair_action=repair_action,
        outcome=outcome,
        embedding=embedding
    )

    session.add(memory)
    try:
        await session.commit()
        return memory
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to save incident memory {incident_id}: {e}")
        return None
