import logging
from typing import Optional
import httpx
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

class EmbeddingSettings(BaseSettings):
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"

    class Config:
        env_prefix = "KAVACH_"

settings = EmbeddingSettings()

async def generate_embedding(text: str) -> Optional[list[float]]:
    """Generates a vector embedding for the given text using Ollama."""
    url = f"{settings.ollama_base_url}/api/embeddings"
    payload = {
        "model": settings.embedding_model,
        "prompt": text
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("embedding")
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None
