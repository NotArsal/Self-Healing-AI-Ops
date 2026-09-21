from fastapi import FastAPI, Request
from pydantic import BaseModel
import time
import random
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mock LLM Gateway")

class ChatRequest(BaseModel):
    messages: list
    model: str = "mock-model"

class ChatResponse(BaseModel):
    id: str
    choices: list

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    logger.info(f"Received request for model {request.model}")
    
    # Simulate processing time (50ms - 200ms)
    time.sleep(random.uniform(0.05, 0.2))
    
    # Simulate occasional errors (1% chance)
    if random.random() < 0.01:
        logger.error("Simulated LLM Gateway Error")
        return {"error": "Simulated internal error"}, 500

    return ChatResponse(
        id="chatcmpl-mock123",
        choices=[{
            "message": {
                "role": "assistant",
                "content": "This is a mock response from the LLM gateway."
            }
        }]
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}
