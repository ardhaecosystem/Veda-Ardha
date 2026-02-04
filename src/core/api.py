"""
FastAPI server providing OpenAI-compatible API for Open-WebUI.
VISION UPGRADE: Now supports Multimodal inputs (Images + Text).
"""

import asyncio
import json
import time
from typing import Optional, List, Union, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog

from dotenv import load_dotenv
import os

from .openrouter_client import OpenRouterClient
from .orchestrator import VedaOrchestrator
from ..brain.memory_manager import MemoryManager

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Global instances
veda: Optional[VedaOrchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global veda

    # Startup: Initialize Veda
    logger.info("veda_initialization_started")
    load_dotenv()

    client = OpenRouterClient(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        daily_budget=float(os.getenv("DAILY_BUDGET_LIMIT", "2.00"))
    )

    memory = MemoryManager(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        falkordb_password=os.getenv("FALKORDB_PASSWORD"),
    )

    await memory.initialize()

    veda = VedaOrchestrator(client, memory)

    logger.info("veda_initialized_successfully")

    yield

    # Shutdown
    logger.info("veda_shutdown_started")
    await memory.close()
    await client.close()
    logger.info("veda_shutdown_complete")


app = FastAPI(
    title="Veda AI API",
    description="OpenAI-compatible API for Veda Memorial AI System",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- UPDATED REQUEST MODELS FOR VISION ---
class ChatMessage(BaseModel):
    role: str
    # CHANGED: Content can now be a string OR a list (for images)
    content: Union[str, List[Dict[str, Any]]]


class ChatCompletionRequest(BaseModel):
    model: str = "veda-v1"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Veda AI",
        "version": "2.0.0"
    }


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI compatibility)."""
    return {
        "object": "list",
        "data": [
            {
                "id": "veda-v1",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "veda",
            }
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint.
    Now handles Vision inputs by extracting text for logic processing
    but passing full multimodal context to the Model.
    """

    if not veda:
        raise HTTPException(status_code=503, detail="Veda is starting up")

    # Extract latest user message
    last_msg = request.messages[-1]
    
    # Logic to extract JUST the text part for Memory/Search systems
    user_text = ""
    has_image = False
    
    if isinstance(last_msg.content, str):
        user_text = last_msg.content
    elif isinstance(last_msg.content, list):
        # Vision Request: Extract text from list format
        has_image = True
        for part in last_msg.content:
            if part.get("type") == "text":
                user_text += part.get("text", "") + " "
    
    user_text = user_text.strip()
    thread_id = "default_thread"  # In production, extract from user ID

    logger.info("incoming_request", message_preview=user_text[:50], has_image=has_image, stream=request.stream)

    # Get the full payload (if it's a list) or None
    full_payload = last_msg.content if has_image else None

    if request.stream:
        return StreamingResponse(
            stream_generator(user_text, thread_id, full_payload),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming fallback
        full_response = ""
        async for token in veda.process_message_streaming(user_text, thread_id, full_message_payload=full_payload):
            full_response += token

        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_response
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }


async def stream_generator(message: str, thread_id: str, full_payload: Optional[List] = None):
    """
    Generate Server-Sent Events (SSE) for Open-WebUI.
    Passes 'full_payload' to enable Vision support.
    """

    chunk_id = f"chatcmpl-{int(time.time())}"

    try:
        async for token in veda.process_message_streaming(message, thread_id, full_message_payload=full_payload):
            chunk_data = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "veda-v1",
                "choices": [{
                    "index": 0,
                    "delta": {"content": token},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"

        # Send finish signal
        final_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "veda-v1",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error("streaming_error", error=str(e))
        error_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "veda-v1",
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n\nError: {str(e)}"},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy" if veda else "initializing",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "orchestrator": veda is not None,
            "openrouter": veda is not None,
            "memory": veda is not None,
        }
    }
