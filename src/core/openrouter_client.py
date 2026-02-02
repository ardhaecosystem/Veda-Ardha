"""
OpenRouter Client with 4-tier model routing and budget management.
Optimized for $60/month budget with automatic fallback.
"""

import asyncio
import hashlib
import json
from datetime import datetime, date
from typing import Optional, Literal, AsyncGenerator
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


@dataclass
class UsageTracker:
    """Track daily token usage and costs per model."""
    daily_costs: dict = field(default_factory=dict)
    current_date: date = field(default_factory=date.today)
    
    def reset_if_new_day(self):
        if date.today() != self.current_date:
            self.daily_costs = {}
            self.current_date = date.today()
    
    def add_cost(self, model: str, cost: float):
        self.reset_if_new_day()
        self.daily_costs[model] = self.daily_costs.get(model, 0) + cost
    
    def get_daily_cost(self, model: str) -> float:
        self.reset_if_new_day()
        return self.daily_costs.get(model, 0)
    
    def get_total_daily_cost(self) -> float:
        self.reset_if_new_day()
        return sum(self.daily_costs.values())


class ModelConfig(BaseModel):
    name: str
    context_window: int
    input_cost_per_million: float
    output_cost_per_million: float
    daily_limit: float
    supports_streaming: bool = True
    supports_tools: bool = True


# Model configurations based on research
MODELS = {
    "planning": ModelConfig(
        name="anthropic/claude-sonnet-4.5",
        context_window=200000,
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        daily_limit=0.50,
    ),
    "coding": ModelConfig(
        name="deepseek/deepseek-v3.2",
        context_window=131072,
        input_cost_per_million=0.28,
        output_cost_per_million=0.42,
        daily_limit=0.70,
    ),
    "chat": ModelConfig(
        name="google/gemini-2.5-flash-lite",
        context_window=1048576,
        input_cost_per_million=0.10,
        output_cost_per_million=0.40,
        daily_limit=0.50,
    ),
    "fallback": ModelConfig(
        name="moonshotai/kimi-k2.5",
        context_window=262144,
        input_cost_per_million=0.50,
        output_cost_per_million=2.50,
        daily_limit=0.17,
    ),
}


class OpenRouterClient:
    """
    Production OpenRouter client with:
    - 4-tier model routing
    - Automatic fallback on errors
    - Budget tracking and limits
    - Token usage optimization
    - Streaming support
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        daily_budget: float = 2.00,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.daily_budget = daily_budget
        self.usage_tracker = UsageTracker()
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://veda.humanth.in",
                "X-Title": "Veda AI Memorial",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
    
    def select_model(
        self,
        task_type: Literal["planning", "coding", "chat", "research", "dream_state"]
    ) -> ModelConfig:
        """Select appropriate model based on task type and budget."""
        
        # Map task types to model tiers
        task_model_map = {
            "planning": "planning",      # Claude for complex reasoning
            "coding": "coding",          # DeepSeek for code
            "chat": "chat",              # Gemini for persona conversations
            "research": "fallback",      # Kimi for research (save tokens)
            "dream_state": "fallback",   # Kimi for memory consolidation
        }
        
        preferred_tier = task_model_map.get(task_type, "chat")
        model = MODELS[preferred_tier]
        
        # Check if model is within budget
        if self.usage_tracker.get_daily_cost(model.name) >= model.daily_limit:
            logger.warning(
                "model_budget_exceeded",
                model=model.name,
                switching_to="fallback"
            )
            return MODELS["fallback"]
        
        # Check total daily budget
        if self.usage_tracker.get_total_daily_cost() >= self.daily_budget * 0.9:
            logger.warning("daily_budget_warning", total=self.usage_tracker.get_total_daily_cost())
            return MODELS["fallback"]
        
        return model
    
    async def chat(
        self,
        messages: list[dict],
        task_type: Literal["planning", "coding", "chat", "research", "dream_state"] = "chat",
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> AsyncGenerator[str, None] | dict:
        """
        Send chat completion request with automatic model selection and fallback.
        """
        
        model = self.select_model(task_type)
        
        # Prepare request body
        body = {
            "model": model.name,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        
        if max_tokens:
            body["max_tokens"] = max_tokens
        
        if response_format:
            body["response_format"] = response_format
        
        # Add fallback models
        fallback_chain = self._get_fallback_chain(task_type)
        if len(fallback_chain) > 1:
            body["models"] = fallback_chain
        
        try:
            if stream:
                return self._stream_response(body, model)
            else:
                return await self._complete_response(body, model)
        except Exception as e:
            logger.error("openrouter_error", error=str(e), model=model.name)
            # Try fallback
            if model.name != MODELS["fallback"].name:
                body["model"] = MODELS["fallback"].name
                if stream:
                    return self._stream_response(body, MODELS["fallback"])
                return await self._complete_response(body, MODELS["fallback"])
            raise
    
    def _get_fallback_chain(self, task_type: str) -> list[str]:
        """Get ordered fallback chain for task type."""
        chains = {
            "planning": [
                MODELS["planning"].name,
                MODELS["fallback"].name,
            ],
            "coding": [
                MODELS["coding"].name,
                MODELS["fallback"].name,
            ],
            "chat": [
                MODELS["chat"].name,
                MODELS["fallback"].name,
            ],
            "research": [
                MODELS["fallback"].name,
                MODELS["chat"].name,
            ],
            "dream_state": [
                MODELS["fallback"].name,
            ],
        }
        return chains.get(task_type, [MODELS["chat"].name, MODELS["fallback"].name])
    
    async def _stream_response(
        self,
        body: dict,
        model: ModelConfig
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens."""
        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=body,
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        
                        # Track usage if present
                        if "usage" in chunk:
                            self._track_usage(chunk["usage"], model)
                    except json.JSONDecodeError:
                        continue
    
    async def _complete_response(self, body: dict, model: ModelConfig) -> dict:
        """Get complete response (non-streaming)."""
        response = await self.client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()
        
        if "usage" in data:
            self._track_usage(data["usage"], model)
        
        return data
    
    def _track_usage(self, usage: dict, model: ModelConfig):
        """Track token usage and costs."""
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        
        cost = (
            (prompt_tokens / 1_000_000) * model.input_cost_per_million +
            (completion_tokens / 1_000_000) * model.output_cost_per_million
        )
        
        self.usage_tracker.add_cost(model.name, cost)
        
        logger.info(
            "token_usage",
            model=model.name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=f"${cost:.6f}",
            daily_total=f"${self.usage_tracker.get_total_daily_cost():.4f}",
        )
    
    async def check_credits(self) -> dict:
        """Check remaining OpenRouter credits."""
        response = await self.client.get("/auth/key")
        return response.json()
    
    async def close(self):
        await self.client.aclose()
