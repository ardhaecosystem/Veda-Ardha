"""
Veda 3.0 API Server: OpenAI-Compatible with Cognitive Architecture
Adds: Emotion persistence, background tasks, Redis integration
"""

import asyncio
import json
import time
import os
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog

from dotenv import load_dotenv

from .openrouter_client import OpenRouterClient
from .orchestrator import VedaOrchestrator
from ..brain.memory_manager import MemoryManager
from ..cognition.emotion_manager import (
    RedisEmotionStore,
    EmotionManager,
    EmotionPromptGenerator,
    VedaEmotionalState,
    EmotionMode,
    PADState
)

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
emotion_store: Optional[RedisEmotionStore] = None
emotion_manager: Optional[EmotionManager] = None
emotion_prompt_gen: Optional[EmotionPromptGenerator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle with Veda 3.0 cognitive features."""
    global veda, emotion_store, emotion_manager, emotion_prompt_gen
    
    logger.info("veda_3.0_initialization_started")
    load_dotenv()
    
    # Initialize core AI components
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
    
    # VEDA 3.0: Initialize cognitive emotion system
    redis_url = os.getenv("COGNITIVE_REDIS_URL", "redis://localhost:6380")
    emotion_store = RedisEmotionStore(redis_url=redis_url)
    emotion_manager = EmotionManager()
    emotion_prompt_gen = EmotionPromptGenerator()
    
    # Test Redis connection
    try:
        await emotion_store.connect()
        logger.info("veda_3.0_emotion_system_online", redis_url=redis_url)
    except Exception as e:
        logger.warning("veda_3.0_emotion_system_degraded", error=str(e))
    
    logger.info("veda_3.0_initialized_successfully")
    
    yield
    
    # Shutdown
    logger.info("veda_3.0_shutdown_started")
    await memory.close()
    await client.close()
    if emotion_store:
        await emotion_store.close()
    logger.info("veda_3.0_shutdown_complete")


app = FastAPI(
    title="Veda 3.0 AI API",
    description="OpenAI-compatible API with Brain-Inspired Cognitive Architecture",
    version="3.0.0",
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


# OpenAI-compatible Request Models
class ChatMessage(BaseModel):
    role: str
    content: str | List[Dict[str, Any]]  # Support multimodal


class ChatCompletionRequest(BaseModel):
    model: str = "veda-v3"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    user: Optional[str] = Field(default="default_user")  # For emotion tracking


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Veda 3.0 AI",
        "version": "3.0.0",
        "features": ["vision", "emotion", "memory", "sap_agent"]
    }


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI compatibility)."""
    return {
        "object": "list",
        "data": [
            {
                "id": "veda-v3",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "veda",
                "description": "Veda 3.0 with cognitive architecture"
            }
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    background_tasks: BackgroundTasks
):
    """
    OpenAI-compatible chat completions endpoint with Veda 3.0 cognitive features.
    
    NEW in 3.0:
    - Persistent emotional state tracking
    - Emotion-aware prompt generation
    - Background emotion updates
    """
    
    if not veda:
        raise HTTPException(status_code=503, detail="Veda is starting up")
    
    # Extract user message (last message)
    user_msg = request.messages[-1].content
    user_id = request.user or "default_user"
    thread_id = f"thread_{user_id}"
    
    # Handle multimodal (vision) content
    full_message_payload = None
    message_text = ""
    
    if isinstance(user_msg, list):
        # Multimodal message - extract text and keep full payload
        full_message_payload = user_msg
        message_text = " ".join([
            item.get("text", "") 
            for item in user_msg 
            if item.get("type") == "text"
        ])
    else:
        # Text-only message
        message_text = user_msg
    
    logger.info(
        "veda_3.0_request",
        user_id=user_id,
        message_preview=message_text[:50],
        has_vision=bool(full_message_payload),
        stream=request.stream
    )
    
    # VEDA 3.0: Load and prepare emotional state
    emotional_context = await prepare_emotional_context(user_id, message_text)
    
    if request.stream:
        return StreamingResponse(
            stream_generator(
                message_text,
                thread_id,
                full_message_payload,
                emotional_context,
                user_id,
                background_tasks
            ),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming fallback
        full_response = ""
        async for token in veda.process_message_streaming(
            message_text, 
            thread_id, 
            full_message_payload
        ):
            full_response += token
        
        # Background: Update emotional state
        background_tasks.add_task(
            update_emotional_state_background,
            user_id,
            message_text,
            full_response,
            emotional_context
        )
        
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


async def prepare_emotional_context(user_id: str, message: str) -> Dict[str, Any]:
    """
    VEDA 3.0: Prepare emotional context for this request.
    
    Returns dict with:
    - state: VedaEmotionalState or None
    - emotion: Current emotion label
    - intensity: Emotional intensity
    - mode: Current mode
    - modifier: Prompt modifier text
    """
    
    if not emotion_store or not emotion_manager or not emotion_prompt_gen:
        return {}
    
    try:
        # Load current state (or create new)
        state = await emotion_store.get_state(user_id)
        
        if not state:
            # First interaction - create neutral state
            state = VedaEmotionalState(
                user_id=user_id,
                session_id="default",
                mode=EmotionMode.PERSONAL,
                pad_state=PADState()
            )
            logger.info("emotion_state_initialized", user_id=user_id)
        else:
            # Apply time-based decay
            state = emotion_manager.apply_decay(state)
        
        # Determine mode from message context
        # (Simple heuristic - can be made more sophisticated)
        has_sap_keywords = any(
            kw in message.lower() 
            for kw in ["sap", "basis", "transaction", "system", "error", "dump"]
        )
        state.mode = EmotionMode.WORK if has_sap_keywords else EmotionMode.PERSONAL
        
        # Generate emotion-aware prompt modifier
        modifier = emotion_prompt_gen.generate_modifier(state)
        
        emotion_context = {
            "state": state,
            "emotion": state.pad_state.to_emotion_label(),
            "intensity": state.pad_state.magnitude(),
            "mode": state.mode.value,
            "modifier": modifier
        }
        
        logger.debug(
            "emotion_context_prepared",
            user_id=user_id,
            emotion=emotion_context["emotion"],
            intensity=f"{emotion_context['intensity']:.2f}",
            mode=emotion_context["mode"]
        )
        
        return emotion_context
        
    except Exception as e:
        logger.error("emotion_context_error", user_id=user_id, error=str(e))
        return {}


async def stream_generator(
    message: str,
    thread_id: str,
    full_message_payload: Optional[List[Dict]],
    emotional_context: Dict[str, Any],
    user_id: str,
    background_tasks: BackgroundTasks
):
    """
    Generate Server-Sent Events (SSE) for Open-WebUI with Veda 3.0 cognitive features.
    """
    
    chunk_id = f"chatcmpl-{int(time.time())}"
    full_response = ""
    
    try:
        # Pass emotional context to orchestrator
        # For now, we'll inject it via veda.persona directly before streaming
        # (In Phase 2, we'll integrate into LangGraph workflow)
        
        async for token in veda.process_message_streaming(
            message, 
            thread_id, 
            full_message_payload
        ):
            full_response += token
            
            chunk_data = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "veda-v3",
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
            "model": "veda-v3",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"
        
        # VEDA 3.0: Schedule emotional state update in background
        background_tasks.add_task(
            update_emotional_state_background,
            user_id,
            message,
            full_response,
            emotional_context
        )
        
    except Exception as e:
        logger.error("streaming_error", error=str(e))
        error_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "veda-v3",
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n\nError: {str(e)}"},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


async def update_emotional_state_background(
    user_id: str,
    message: str,
    response: str,
    emotional_context: Dict[str, Any]
):
    """
    VEDA 3.0: Update emotional state based on conversation.
    Runs in background to not block response.
    
    This is where emotion triggers are detected and applied.
    """
    
    if not emotion_store or not emotion_manager:
        return
    
    try:
        state = emotional_context.get("state")
        if not state:
            return
        
        # Detect emotional trigger from conversation
        trigger = emotion_manager.detect_trigger_from_message(message, response)
        
        if trigger:
            # Apply trigger with appropriate intensity
            intensity = 1.0
            
            # Modulate intensity based on message characteristics
            if len(message.split()) > 100:
                intensity *= 1.2  # More intense for longer, detailed messages
            if any(word in message.lower() for word in ["urgent", "critical", "asap"]):
                intensity *= 1.3  # Higher intensity for urgent matters
            
            state = emotion_manager.apply_trigger(state, trigger, intensity)
            
            logger.info(
                "emotion_triggered",
                user_id=user_id,
                trigger=trigger,
                new_emotion=state.pad_state.to_emotion_label(),
                intensity=intensity
            )
        
        # Save updated state
        await emotion_store.save_state(state)
        
    except Exception as e:
        logger.error("emotion_update_error", user_id=user_id, error=str(e))


@app.get("/health")
async def health_check():
    """Detailed health check with Veda 3.0 status."""
    emotion_status = "unknown"
    
    if emotion_store:
        try:
            await emotion_store.connect()
            emotion_status = "healthy"
        except:
            emotion_status = "degraded"
    
    return {
        "status": "healthy" if veda else "initializing",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "components": {
            "orchestrator": veda is not None,
            "openrouter": veda is not None,
            "memory": veda is not None,
            "emotion_system": emotion_status,  # NEW in 3.0
        },
        "features": {
            "vision": True,
            "emotion": emotion_status == "healthy",
            "memory": True,
            "sap_agent": True,
            "streaming": True
        }
    }


@app.get("/v1/emotion/status/{user_id}")
async def get_emotion_status(user_id: str):
    """
    VEDA 3.0: Check current emotional state for a user.
    Useful for debugging and monitoring.
    """
    
    if not emotion_store:
        raise HTTPException(status_code=503, detail="Emotion system not available")
    
    try:
        state = await emotion_store.get_state(user_id)
        
        if not state:
            return {
                "user_id": user_id,
                "status": "no_state",
                "message": "No emotional state found for this user"
            }
        
        # Apply decay to get current state
        state = emotion_manager.apply_decay(state)
        
        return {
            "user_id": user_id,
            "status": "active",
            "emotion": state.pad_state.to_emotion_label(),
            "intensity": state.pad_state.magnitude(),
            "pad_state": {
                "pleasure": state.pad_state.pleasure,
                "arousal": state.pad_state.arousal,
                "dominance": state.pad_state.dominance
            },
            "mode": state.mode.value,
            "last_update": state.last_update.isoformat(),
            "last_trigger": state.trigger_event
        }
        
    except Exception as e:
        logger.error("emotion_status_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/emotion/reset/{user_id}")
async def reset_emotion(user_id: str):
    """
    VEDA 3.0: Reset emotional state to neutral.
    Useful for testing or user request.
    """
    
    if not emotion_store:
        raise HTTPException(status_code=503, detail="Emotion system not available")
    
    try:
        success = await emotion_store.delete_state(user_id)
        
        if success:
            return {
                "user_id": user_id,
                "status": "reset",
                "message": "Emotional state reset to neutral"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to reset state")
            
    except Exception as e:
        logger.error("emotion_reset_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
