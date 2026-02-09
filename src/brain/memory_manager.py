"""
Veda Brain - Memory System using Graphiti + FalkorDB.
LIGHTWEIGHT VERSION: Compression moved to TokenOptimizer.
MAINTENANCE UPDATE: Added consolidate_memories for Dream State.
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
import structlog
from .associative_memory import get_associations, Association

logger = structlog.get_logger()

@dataclass
class MemoryEntry:
    content: str
    memory_type: str
    timestamp: datetime
    importance: float
    metadata: dict

class MemoryManager:
    """
    Brain-inspired memory system.
    - Separate episodic memory for Personal and Work modes.
    - Bi-temporal tracking.
    - Selective storage (Importance Scoring).
    """

    def __init__(
        self,
        openrouter_api_key: str,
        falkordb_host: str = "localhost",
        falkordb_port: int = 6379,
        falkordb_password: Optional[str] = None,
    ):
        self.openrouter_key = openrouter_api_key

        # Initialize separate Graphiti instances for memory isolation
        self.personal_graphiti = self._create_graphiti(
            falkordb_host, falkordb_port, falkordb_password,
            database="personal_memory"
        )
        self.work_graphiti = self._create_graphiti(
            falkordb_host, falkordb_port, falkordb_password,
            database="work_memory"
        )

        logger.info("memory_manager_initialized")

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
            model="deepseek/deepseek-v3.2",
            small_model="deepseek/deepseek-v3.2",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.1,
        )
        llm_client = OpenAIGenericClient(config=llm_config)

        # Configure embedder (OpenRouter/OpenAI compatible)
        embedder_config = OpenAIEmbedderConfig(
            api_key=self.openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            embedding_model="text-embedding-3-small",
            embedding_dim=1536,
        )
        embedder = OpenAIEmbedder(config=embedder_config)

        # Configure cross-encoder
        cross_encoder_config = LLMConfig(
            api_key=self.openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            model="deepseek/deepseek-v3.2",
        )
        cross_encoder = OpenAIRerankerClient(config=cross_encoder_config)

        driver = FalkorDriver(host=host, port=port, password=password, database=database)

        return Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )

    async def initialize(self):
        await self.personal_graphiti.build_indices_and_constraints()
        await self.work_graphiti.build_indices_and_constraints()
        logger.info("memory_indices_built")

    def _get_graphiti(self, memory_type: Literal["personal", "work"]) -> Graphiti:
        return self.personal_graphiti if memory_type == "personal" else self.work_graphiti

    async def store(
        self,
        user_message: str,
        assistant_response: str,
        memory_type: Literal["personal", "work"],
        metadata: Optional[dict] = None,
    ):
        """Store conversation in appropriate memory space based on importance."""
        importance = await self._calculate_importance(user_message, assistant_response, memory_type)

        if importance < 0.3:
            return

        graphiti = self._get_graphiti(memory_type)
        episode_content = f"""User: {user_message}\nAssistant: {assistant_response}"""

        await graphiti.add_episode(
            name=f"{memory_type}_conversation_{datetime.now().isoformat()}",
            episode_body=episode_content,
            reference_time=datetime.now(),
            source_description=f"Conversation in {memory_type} mode",
        )

    async def search(
        self,
        query: str,
        memory_type: Literal["personal", "work"],
        limit: int = 5,
    ) -> list[dict]:
        """Search memories using semantic search."""
        graphiti = self._get_graphiti(memory_type)
        results = await graphiti.search(query=query, num_results=limit)

        memories = []
        for result in results:
            memories.append({
                "content": result.fact if hasattr(result, 'fact') else str(result),
                "timestamp": result.created_at if hasattr(result, 'created_at') else datetime.now(),
            })
        return memories

    # --- NEW METHOD ADDED FOR DREAM STATE ---
    async def consolidate_memories(self, memory_type: Literal["personal", "work"]):
        """
        Trigger maintenance for the memory graph.
        Called by nightly dream state.
        """
        # For now, we log the activity. Graphiti handles index management internally
        # during insertion, but this is a placeholder for future deep-cleanup jobs.
        logger.info("memory_consolidation_active", type=memory_type)
        return True

    async def _calculate_importance(self, user_message: str, assistant_response: str, memory_type: str) -> float:
        msg_len = len(user_message) + len(assistant_response)
        if msg_len < 50: return 0.1
        if memory_type == "work" and any(k in user_message.lower() for k in ["sap", "error", "code"]): return 0.9
        if memory_type == "personal" and any(k in user_message.lower() for k in ["love", "feel", "miss"]): return 0.8
        return 0.5


    async def get_associated_memories(
        self,
        query: str,
        direct_memories: list[dict],
        memory_type: Literal["personal", "work"],
        max_hops: int = 2,
        min_relevance: float = 0.6
    ) -> list:
        """
        Find semantically associated memories using spreading activation.

        Phase 3: Associative Memory - finds related memories through graph traversal.

        Args:
            query: User's current query
            direct_memories: Results from search() method
            memory_type: "personal" or "work"
            max_hops: Graph traversal depth (1-3, default 2)
            min_relevance: Minimum relevance score (0.0-1.0, default 0.6)

        Returns:
            List of Association objects with content, relevance, reasoning
        """

        if not direct_memories:
            logger.debug("no_direct_memories_for_association", memory_type=memory_type)
            return []

        try:
            # Get the appropriate graphiti instance
            graphiti = self._get_graphiti(memory_type)

            # Use associative retrieval from File 1
            associations = await get_associations(
                query=query,
                existing_memories=direct_memories,
                graph_driver=graphiti.driver,
                memory_type=memory_type,
                max_hops=max_hops,
                min_relevance=min_relevance
            )

            logger.info(
                "associative_retrieval_complete",
                memory_type=memory_type,
                associations_found=len(associations)
            )

            return associations

        except Exception as e:
            logger.error(
                "associative_retrieval_error",
                memory_type=memory_type,
                error=str(e)
            )
            return []

    # ============================================================================
    # PHASE 4: CURIOSITY & LEARNING METHODS
    # ============================================================================

    async def store_clarification(
        self,
        original_query: str,
        clarification_question: str,
        user_answer: str,
        memory_type: Literal["personal", "work"],
        uncertainty_score: float = 0.0
    ):
        """Store a clarification interaction for learning."""
        
        clarification_entry = f"""
        [CLARIFICATION INTERACTION]
        Original Query: {original_query}
        Veda Asked: {clarification_question}
        User Clarified: {user_answer}
        Uncertainty Score: {uncertainty_score:.2f}
        
        This interaction taught me to ask for specifics when users say things like
        "{original_query[:50]}..." without providing necessary context.
        """
        
        graphiti = self._get_graphiti(memory_type)
        
        await graphiti.add_episode(
            name=f"clarification_{memory_type}_{datetime.now().isoformat()}",
            episode_body=clarification_entry,
            reference_time=datetime.now(),
            source_description=f"Phase 4 clarification learning in {memory_type} mode",
        )
        
        logger.info(
            "clarification_stored",
            memory_type=memory_type,
            uncertainty=f"{uncertainty_score:.2f}",
            query_preview=original_query[:50]
        )

    async def get_past_clarifications(
        self,
        query: str,
        memory_type: Literal["personal", "work"],
        limit: int = 3
    ) -> list[dict]:
        """Retrieve past clarification patterns."""
        
        graphiti = self._get_graphiti(memory_type)
        search_query = f"clarification interaction {query}"
        results = await graphiti.search(query=search_query, num_results=limit)
        
        clarifications = []
        for result in results:
            content = result.fact if hasattr(result, 'fact') else str(result)
            if "CLARIFICATION INTERACTION" in content:
                clarifications.append({
                    "content": content,
                    "timestamp": result.created_at if hasattr(result, 'created_at') else datetime.now(),
                })
        
        return clarifications

    async def store_knowledge_gap(
        self,
        topic: str,
        gap_description: str,
        memory_type: Literal["personal", "work"],
        priority: float = 0.5
    ):
        """Store identified knowledge gap."""
        
        gap_entry = f"""
        [KNOWLEDGE GAP]
        Topic: {topic}
        Gap: {gap_description}
        Priority: {priority:.2f}
        """
        
        graphiti = self._get_graphiti(memory_type)
        
        await graphiti.add_episode(
            name=f"knowledge_gap_{memory_type}_{datetime.now().isoformat()}",
            episode_body=gap_entry,
            reference_time=datetime.now(),
            source_description=f"Phase 4 knowledge gap in {memory_type} mode",
        )

    async def get_knowledge_gaps(
        self,
        memory_type: Literal["personal", "work"],
        limit: int = 5
    ) -> list[dict]:
        """Retrieve stored knowledge gaps."""
        
        graphiti = self._get_graphiti(memory_type)
        results = await graphiti.search(query="knowledge gap priority", num_results=limit)
        
        gaps = []
        for result in results:
            content = result.fact if hasattr(result, 'fact') else str(result)
            if "KNOWLEDGE GAP" in content:
                gaps.append({
                    "content": content,
                    "timestamp": result.created_at if hasattr(result, 'created_at') else datetime.now(),
                })
        
        return gaps

    async def close(self):
        await self.personal_graphiti.close()
        await self.work_graphiti.close()
