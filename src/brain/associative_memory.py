"""
Veda Phase 3: Associative Memory System
Implements spreading activation for semantic memory traversal.

This enables Veda to naturally recall related memories without being asked:
"Oh btw pops, this reminds me of when you mentioned..."
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()


@dataclass
class Association:
    """
    Represents a discovered semantic association.
    
    Attributes:
        content: The associated memory content
        relevance_score: 0.0-1.0 confidence score
        reasoning: Why this association was made
        source_entity: Entity that triggered the association
        target_entity: Entity that was discovered
        relationship_path: How we got there (e.g., ["performance", "RELATES_TO", "database"])
        timestamp: When the associated memory was created
    """
    content: str
    relevance_score: float
    reasoning: str
    source_entity: str
    target_entity: str
    relationship_path: List[str]
    timestamp: datetime


class AssociativeRetriever:
    """
    Spreading activation retrieval for semantic memory connections.
    
    Works with Graphiti's existing graph structure:
    - Entities: Extracted concepts (people, places, technical terms)
    - RELATES_TO: Semantic connections between entities
    - MENTIONS: Episodes that reference entities
    - Episodic: Conversation episodes
    
    Algorithm:
    1. Extract entities from current query
    2. Find direct matches (already done by memory_manager.search())
    3. Traverse RELATES_TO edges to find related entities (NEW)
    4. Find episodes that MENTION those related entities
    5. Score relevance and filter
    6. Return top 1-2 associations
    """
    
    def __init__(
        self,
        max_hops: int = 2,
        min_relevance: float = 0.6,
        max_associations: int = 2,
        activation_decay: float = 0.5
    ):
        """
        Initialize associative retriever.
        
        Args:
            max_hops: Maximum graph traversal depth (1-3, default 2)
            min_relevance: Minimum relevance score to return (0.0-1.0, default 0.6)
            max_associations: Maximum associations to return per query (default 2)
            activation_decay: How much activation decays per hop (default 0.5)
        """
        self.max_hops = max_hops
        self.min_relevance = min_relevance
        self.max_associations = max_associations
        self.activation_decay = activation_decay
        
        logger.info(
            "associative_retriever_initialized",
            max_hops=max_hops,
            min_relevance=min_relevance,
            max_associations=max_associations
        )
    
    async def find_associations(
        self,
        query: str,
        existing_memories: List[Dict],
        graph_driver,
        memory_type: str = "personal"
    ) -> List[Association]:
        """
        Find semantic associations for the given query.
        
        Args:
            query: User's current message
            existing_memories: Direct memory matches (from memory_manager.search())
            graph_driver: FalkorDB driver from Graphiti
            memory_type: "personal" or "work"
            
        Returns:
            List of Association objects, sorted by relevance
        """
        
        if not existing_memories:
            logger.debug("no_existing_memories_to_associate")
            return []
        
        start_time = datetime.now()
        
        try:
            # Step 1: Extract entity names from existing memories
            source_entities = await self._extract_entities_from_memories(
                existing_memories,
                graph_driver,
                memory_type
            )
            
            if not source_entities:
                logger.debug("no_entities_extracted_from_memories")
                return []
            
            # Step 2: Traverse graph to find related entities
            related_entities = await self._traverse_for_related_entities(
                source_entities,
                graph_driver,
                memory_type
            )
            
            if not related_entities:
                logger.debug("no_related_entities_found")
                return []
            
            # Step 3: Find episodes that mention related entities
            associated_episodes = await self._find_episodes_mentioning_entities(
                related_entities,
                graph_driver,
                memory_type
            )
            
            if not associated_episodes:
                logger.debug("no_associated_episodes_found")
                return []
            
            # Step 4: Score and filter associations
            associations = self._score_associations(
                associated_episodes,
                query,
                source_entities,
                related_entities
            )
            
            # Step 5: Filter by relevance and limit
            filtered = [a for a in associations if a.relevance_score >= self.min_relevance]
            top_associations = sorted(filtered, key=lambda x: x.relevance_score, reverse=True)[:self.max_associations]
            
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(
                "associative_retrieval_complete",
                memory_type=memory_type,
                source_entities_count=len(source_entities),
                related_entities_count=len(related_entities),
                episodes_found=len(associated_episodes),
                associations_returned=len(top_associations),
                processing_ms=f"{elapsed_ms:.1f}"
            )
            
            return top_associations
            
        except Exception as e:
            logger.error("associative_retrieval_error", error=str(e))
            return []
    
    async def _extract_entities_from_memories(
        self,
        memories: List[Dict],
        graph_driver,
        memory_type: str
    ) -> List[str]:
        """
        Extract entity names from memory content.
        
        Uses raw Cypher with proper FalkorDriver API.
        Fallback: Returns generic starting points if extraction fails.
        """
        
        entity_names = set()
        
        # Strategy 1: Try to extract entities via raw Cypher
        try:
            # Get all entities and their connection counts
            # FalkorDriver.execute_query(query_string) - takes just the query
            query = f"""
            MATCH (e:Entity)-[r:RELATES_TO]->()
            WITH e.name as entity_name, count(r) as connections
            ORDER BY connections DESC
            RETURN entity_name
            LIMIT 10
            """
            
            # Execute using correct API (just query string, driver handles database selection)
            result = await graph_driver.execute_query(query)
            
            if result and hasattr(result, 'result_set'):
                # Parse FalkorDB result format
                for row in result.result_set:
                    if row and len(row) > 0 and row[0]:
                        entity_names.add(row[0])
            elif result:
                # Alternative format
                for row in result:
                    if row and len(row) > 0 and row[0]:
                        entity_names.add(row[0])
                        
        except Exception as e:
            logger.debug("entity_query_failed", error=str(e))
        
        # Strategy 2: If no entities found, use memory content keywords as pseudo-entities
        if not entity_names:
            logger.debug("entity_extraction_fallback", reason="query_failed_using_keywords")
            
            # Extract meaningful keywords from memories as starting points
            for memory in memories[:3]:
                content = memory.get('content', '')
                words = content.lower().split()
                
                # Get capitalized words or technical terms (likely entity names)
                for word in words[:20]:
                    cleaned = word.strip('.,!?;:\'\"()[]{}')
                    if len(cleaned) > 4 and (
                        word[0].isupper() or  # Capitalized
                        any(term in cleaned for term in ['sap', 'system', 'server', 'database', 'performance'])
                    ):
                        entity_names.add(cleaned)
        
        entities = list(entity_names)[:5]
        
        logger.debug(
            "entities_extracted",
            count=len(entities),
            entities=entities
        )
        
        return entities
    
    async def _traverse_for_related_entities(
        self,
        source_entities: List[str],
        graph_driver,
        memory_type: str
    ) -> List[Tuple[str, str, List[str]]]:
        """
        Traverse RELATES_TO relationships to find semantically related entities.
        
        Args:
            source_entities: Starting entity names
            graph_driver: FalkorDB driver
            memory_type: "personal" or "work"
            
        Returns:
            List of tuples: (source_entity, target_entity, relationship_path)
        """
        
        related_entities = []
        
        for source in source_entities:
            # Build query for this source entity
            query = f"""
            MATCH (source:Entity)-[r:RELATES_TO*1..{self.max_hops}]->(target:Entity)
            WHERE source.name = '{source}' AND source.name <> target.name
            RETURN source.name as source, 
                   target.name as target,
                   'RELATES_TO' as path
            LIMIT 10
            """
            
            try:
                result = await graph_driver.execute_query(query)
                
                # Parse result
                if result and hasattr(result, 'result_set'):
                    for row in result.result_set:
                        if row and len(row) >= 3:
                            related_entities.append((row[0], row[1], ["RELATES_TO"]))
                elif result:
                    for row in result:
                        if row and len(row) >= 3:
                            related_entities.append((row[0], row[1], ["RELATES_TO"]))
                            
            except Exception as e:
                logger.debug("traverse_error", source=source, error=str(e))
                continue
        
        logger.debug(
            "related_entities_found",
            count=len(related_entities),
            sample=related_entities[:3] if related_entities else []
        )
        
        return related_entities
    
    async def _find_episodes_mentioning_entities(
        self,
        related_entities: List[Tuple[str, str, List[str]]],
        graph_driver,
        memory_type: str
    ) -> List[Dict]:
        """
        Find episodic memories that mention the related entities.
        
        Args:
            related_entities: List of (source, target, path) tuples
            graph_driver: FalkorDB driver
            memory_type: "personal" or "work"
            
        Returns:
            List of episode dicts with metadata
        """
        
        episodes = []
        seen_names = set()
        
        for source, target, path in related_entities:
            # Find episodes mentioning this target entity
            query = f"""
            MATCH (entity:Entity)<-[:MENTIONS]-(episode:Episodic)
            WHERE entity.name = '{target}'
            RETURN episode.name as episode_name,
                   episode.content as content,
                   episode.created_at as created_at
            LIMIT 5
            """
            
            try:
                result = await graph_driver.execute_query(query)
                
                # Parse result
                if result and hasattr(result, 'result_set'):
                    for row in result.result_set:
                        if row and len(row) >= 3:
                            episode_name = row[0]
                            if episode_name not in seen_names:
                                seen_names.add(episode_name)
                                episodes.append({
                                    'source_entity': source,
                                    'target_entity': target,
                                    'relationship_path': path,
                                    'episode_name': episode_name,
                                    'content': row[1] or "",
                                    'created_at': row[2] or datetime.now().isoformat()
                                })
                elif result:
                    for row in result:
                        if row and len(row) >= 3:
                            episode_name = row[0]
                            if episode_name not in seen_names:
                                seen_names.add(episode_name)
                                episodes.append({
                                    'source_entity': source,
                                    'target_entity': target,
                                    'relationship_path': path,
                                    'episode_name': episode_name,
                                    'content': row[1] or "",
                                    'created_at': row[2] or datetime.now().isoformat()
                                })
                            
            except Exception as e:
                logger.debug("episode_query_error", target=target, error=str(e))
                continue
        
        logger.debug("episodes_retrieved", count=len(episodes))
        
        return episodes
    
    def _score_associations(
        self,
        episodes: List[Dict],
        query: str,
        source_entities: List[str],
        related_entities: List[Tuple[str, str, List[str]]]
    ) -> List[Association]:
        """
        Score the relevance of discovered associations.
        
        Scoring factors:
        1. Path length (shorter = more relevant)
        2. Temporal recency (recent = more relevant)
        3. Content similarity (keyword overlap)
        4. Entity importance (frequency in graph)
        """
        
        associations = []
        query_lower = query.lower()
        
        for episode in episodes:
            # Base score from activation decay
            path = episode.get('relationship_path', ['RELATES_TO'])
            hops = len(path)
            activation_score = self.activation_decay ** hops
            
            # Temporal recency score (last 7 days = 1.0, older = decay)
            try:
                created_at = datetime.fromisoformat(episode['created_at'])
                days_ago = (datetime.now() - created_at).days
                recency_score = max(0.0, 1.0 - (days_ago / 30.0))  # Decay over 30 days
            except:
                recency_score = 0.5  # Default for parsing errors
            
            # Content similarity (simple keyword overlap)
            content_lower = episode.get('content', '').lower()
            query_words = set(query_lower.split())
            content_words = set(content_lower.split())
            overlap = len(query_words & content_words)
            similarity_score = min(1.0, overlap / max(len(query_words), 1) * 2.0)
            
            # Combined relevance score (weighted average)
            relevance_score = (
                activation_score * 0.4 +
                recency_score * 0.3 +
                similarity_score * 0.3
            )
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                episode['source_entity'],
                episode['target_entity'],
                path,
                days_ago if 'days_ago' in locals() else 0
            )
            
            association = Association(
                content=episode['content'][:300],  # Limit length
                relevance_score=relevance_score,
                reasoning=reasoning,
                source_entity=episode['source_entity'],
                target_entity=episode['target_entity'],
                relationship_path=[episode['source_entity']] + path + [episode['target_entity']],
                timestamp=created_at if 'created_at' in locals() else datetime.now()
            )
            
            associations.append(association)
        
        return associations
    
    def _generate_reasoning(
        self,
        source: str,
        target: str,
        path: List[str],
        days_ago: int
    ) -> str:
        """
        Generate human-readable reasoning for the association.
        
        This helps Veda explain WHY she's bringing up this memory.
        """
        
        hops = len(path)
        
        if hops == 1:
            reasoning = f"directly related to {source}"
        else:
            reasoning = f"connected through {' → '.join(path)} from {source}"
        
        if days_ago == 0:
            time_context = "earlier today"
        elif days_ago == 1:
            time_context = "yesterday"
        elif days_ago < 7:
            time_context = f"{days_ago} days ago"
        else:
            time_context = f"about {days_ago // 7} weeks ago"
        
        return f"This came up {time_context}, {reasoning}"


# Convenience function for orchestrator
async def get_associations(
    query: str,
    existing_memories: List[Dict],
    graph_driver,
    memory_type: str = "personal",
    max_hops: int = 2,
    min_relevance: float = 0.6
) -> List[Association]:
    """
    Convenience function to get associations.
    
    Usage in orchestrator:
        associations = await get_associations(
            query=message,
            existing_memories=personal_memories,
            graph_driver=self.memory.personal_graphiti.driver,
            memory_type="personal"
        )
    """
    retriever = AssociativeRetriever(
        max_hops=max_hops,
        min_relevance=min_relevance
    )
    
    return await retriever.find_associations(
        query=query,
        existing_memories=existing_memories,
        graph_driver=graph_driver,
        memory_type=memory_type
    )
