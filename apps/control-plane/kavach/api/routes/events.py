import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from kavach.api.store import EVENT_QUEUES

router = APIRouter(prefix="/events", tags=["events"])

class CustomEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        # Check if it has a model_dump method (Pydantic v2)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return super().default(obj)

from typing import Any, AsyncGenerator

@router.get("/stream")
async def event_stream(request: Request) -> Any:
    """Server-Sent Events stream for live graph updates."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    EVENT_QUEUES.append(queue)
    
    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                event_data = await queue.get()
                
                yield {
                    "event": "message",
                    "data": json.dumps(event_data, cls=CustomEncoder)
                }
        finally:
            EVENT_QUEUES.remove(queue)
            
    return EventSourceResponse(event_generator())
