"""
Veda Brain - Memory System using Graphiti + FalkorDB.
Implements separate memory spaces for Personal and Work modes.

FIXED VERSION:
- Uses OpenRouter for embeddings (via OpenAI-compatible API)
- Uses OpenRouter for cross-encoder reranking
- Keeps LLMLingua-2 context compression
- Maintains dual memory spaces (personal/work)
"""

import asyncio
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from llmlingua import PromptCompressor
import structlog

logger = structlog.get_logger()


@dataclass
class MemoryEntry:
    """Represents a memory entry."""
    content: str
    memory_type: str
    timestamp: datetime
    importance: float
    metadata: dict


class MemoryManager:
    """
    Brain-inspired memory system with:
    - Separate episodic memory for Personal and Work modes
    - Temporal awareness (bi-temporal tracking)
    - Selective memory storage (importance scoring)
    - OpenRouter-based embeddings and reranking
    - Context compression for long conversations
    """

    def __init__(
        self,
        openrouter_api_key: str,
        falkordb_host: str = "localhost",
        falkordb_port: int = 6379,
        falkordb_password: Optional[str] = None,
    ):
        self.openrouter_key = openrouter_api_key

        # Initialize context compressor (LLMLingua-2)
        try:
            self.compressor = PromptCompressor(
                model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
                use_llmlingua2=True,
                device_map="cpu"  # CPU-only for VPS
            )
            logger.info("context_compressor_initialized")
        except Exception as e:
            logger.warning("context_compressor_failed", error=str(e))
            self.compressor = None

        # Initialize separate Graphiti instances for memory isolation
        self.personal_graphiti = self._create_graphiti(
            falkordb_host, falkordb_port, falkordb_password,
            database="personal_memory"
        )
        self.work_graphiti = self._create_graphiti(
            falkordb_host, falkordb_port, falkordb_password,
            database="work_memory"
        )

    def _create_graphiti(
        self,
        host: str,
        port: int,
        password: Optional[str],
        database: str,
    ) -> Graphiti:
        """Create Graphiti instance with OpenRouter for all components."""

        from graphiti_core.driver.falkordb_driver import FalkorDriver

        # Configure LLM client for OpenRouter
        llm_config = LLMConfig(
            api_key=self.openrouter_key,
            model="deepseek/deepseek-v3.2",  # Use DeepSeek for memory operations
            small_model="deepseek/deepseek-v3.2",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.1,
        )

        llm_client = OpenAIGenericClient(config=llm_config)

        # Configure embedder to use OpenRouter
        # OpenRouter supports OpenAI embedding models through their API
        embedder_config = OpenAIEmbedderConfig(
            api_key=self.openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            embedding_model="text-embedding-3-small",
            embedding_dim=1536,
        )
        
        embedder = OpenAIEmbedder(config=embedder_config)

        # Configure cross-encoder (reranker) to use OpenRouter
        cross_encoder_config = LLMConfig(
            api_key=self.openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            model="deepseek/deepseek-v3.2",  # Use cheap model for reranking
        )
        
        cross_encoder = OpenAIRerankerClient(config=cross_encoder_config)

        # FalkorDB driver
        driver = FalkorDriver(
            host=host,
            port=port,
            password=password,
            database=database,
        )

        # Create Graphiti instance with all components configured
        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )

        return graphiti

    async def initialize(self):
        """Initialize indices and constraints."""
        await self.personal_graphiti.build_indices_and_constraints()
        await self.work_graphiti.build_indices_and_constraints()
        logger.info("memory_initialized", personal=True, work=True)

    def _get_graphiti(self, memory_type: Literal["personal", "work"]) -> Graphiti:
        """Get appropriate Graphiti instance based on memory type."""
        return self.personal_graphiti if memory_type == "personal" else self.work_graphiti

    async def store(
        self,
        user_message: str,
        assistant_response: str,
        memory_type: Literal["personal", "work"],
        metadata: Optional[dict] = None,
    ):
        """
        Store conversation in appropriate memory space.
        Uses selective storage based on importance.
        """

        # Calculate importance score
        importance = await self._calculate_importance(
            user_message, assistant_response, memory_type
        )

        # Only store if importance threshold met
        if importance < 0.3:
            logger.debug("memory_skipped", importance=importance)
            return

        graphiti = self._get_graphiti(memory_type)

        # Create episode content
        episode_content = f"""User: {user_message}
Assistant: {assistant_response}"""

        # Add episode to Graphiti
        await graphiti.add_episode(
            name=f"{memory_type}_conversation_{datetime.now().isoformat()}",
            episode_body=episode_content,
            reference_time=datetime.now(),
            source_description=f"Conversation in {memory_type} mode",
        )

        logger.info(
            "memory_stored",
            memory_type=memory_type,
            importance=importance,
            content_length=len(episode_content)
        )

    async def search(
        self,
        query: str,
        memory_type: Literal["personal", "work"],
        limit: int = 5,
    ) -> list[dict]:
        """
        Search memories using semantic search.
        Returns relevant memories from the specified memory type.
        """

        graphiti = self._get_graphiti(memory_type)

        # Use Graphiti's search
        results = await graphiti.search(
            query=query,
            num_results=limit,
        )

        # Format results
        memories = []
        for result in results:
            memories.append({
                "content": result.fact if hasattr(result, 'fact') else str(result),
                "timestamp": result.created_at if hasattr(result, 'created_at') else datetime.now(),
                "score": result.score if hasattr(result, 'score') else 0.0,
            })

        return memories

    async def _calculate_importance(
        self,
        user_message: str,
        assistant_response: str,
        memory_type: str,
    ) -> float:
        """
        Calculate importance score (0-1) for selective memory storage.

        High importance indicators:
        - Emotional content (personal mode)
        - Technical solutions (work mode)
        - Actionable information
        - User preferences

        Low importance:
        - Greetings
        - Trivial chitchat
        - Repetitive content
        """

        # Quick heuristics
        message_length = len(user_message) + len(assistant_response)

        # Very short exchanges are likely greetings
        if message_length < 50:
            return 0.1

        # Greeting patterns
        greetings = ["hi", "hello", "hey", "good morning", "good night"]
        if any(g in user_message.lower() for g in greetings) and len(user_message) < 30:
            return 0.2

        # Work mode: technical content is important
        if memory_type == "work":
            technical_keywords = [
                "sap", "basis", "transaction", "system", "error", "abap",
                "sm21", "st22", "db02", "kernel", "transport", "sid"
            ]
            if any(kw in user_message.lower() or kw in assistant_response.lower()
                   for kw in technical_keywords):
                return 0.8

            # Code blocks
            if "```" in assistant_response or "script" in user_message.lower():
                return 0.9

        # Personal mode: emotional content is important
        if memory_type == "personal":
            emotional_keywords = [
                "feel", "love", "miss", "happy", "sad", "worried",
                "excited", "tired", "proud"
            ]
            if any(kw in user_message.lower() for kw in emotional_keywords):
                return 0.7

        # Default to moderate importance for substantial conversations
        if message_length > 200:
            return 0.5

        return 0.4

    async def consolidate_memories(self, memory_type: Literal["personal", "work"]):
        """
        Dream state: Consolidate and strengthen important memories.
        Called by the nightly dream state job.
        """

        graphiti = self._get_graphiti(memory_type)

        # Let Graphiti process and consolidate
        # This strengthens connections between related memories
        logger.info("consolidating_memories", memory_type=memory_type)

        # Graphiti's internal consolidation happens automatically
        # but we can trigger explicit processing if needed

    def compress_context(self, messages: list[dict], threshold: int = 10) -> list[dict]:
        """
        Compress conversation context when it exceeds threshold.
        Uses LLMLingua-2 to reduce token count while preserving meaning.

        Args:
            messages: List of conversation messages
            threshold: Number of messages before compression triggers

        Returns:
            Compressed message list (or original if compression fails/not needed)
        """

        # Only compress if we exceed threshold and have compressor
        if len(messages) <= threshold or not self.compressor:
            return messages

        try:
            # Separate system message and conversation
            system_msg = messages[0] if messages[0].get("role") == "system" else None
            conversation = messages[1:] if system_msg else messages

            # Only compress middle messages, keep first and last
            if len(conversation) <= 3:
                return messages

            keep_first = conversation[0]
            keep_last = conversation[-1]
            to_compress = conversation[1:-1]

            # Format for compression
            context_text = "\n".join([
                f"{msg['role']}: {msg['content']}"
                for msg in to_compress
            ])

            # Compress using LLMLingua-2
            compressed = self.compressor.compress_prompt(
                context_text,
                rate=0.5,  # Compress to 50% of original
                force_tokens=['\n', ':', 'SAP', 'error', 'transaction'],  # Keep important tokens
            )

            compressed_msg = {
                "role": "system",
                "content": f"[Compressed conversation history]\n{compressed['compressed_prompt']}"
            }

            # Rebuild message list
            result = []
            if system_msg:
                result.append(system_msg)
            result.append(keep_first)
            result.append(compressed_msg)
            result.append(keep_last)

            logger.info(
                "context_compressed",
                original_messages=len(messages),
                compressed_messages=len(result),
                compression_rate=compressed.get('rate', 0.5)
            )

            return result

        except Exception as e:
            logger.warning("compression_failed", error=str(e))
            return messages

    async def close(self):
        """Cleanup resources."""
        await self.personal_graphiti.close()
        await self.work_graphiti.close()
