"""
Veda Phase 4: Question Queue
Redis-based queue for pending clarification questions.

Features:
- Priority scoring (importance × urgency)
- Cooldown management (prevents rapid-fire questions)
- Deduplication (avoids asking same question twice)
- Persistence (survives restarts)
- Async operations (non-blocking)

Design philosophy:
- Questions are queued when timing isn't perfect
- Retrieved when conversation flow allows
- Expired after reasonable time (24 hours)
"""

import json
import asyncio
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import structlog
import redis.asyncio as aioredis

logger = structlog.get_logger()


@dataclass
class PendingQuestion:
    """
    A question waiting to be asked.
    
    Attributes:
        question_id: Unique identifier
        question_text: The actual question
        conversation_id: Which conversation this belongs to
        user_id: User identifier
        priority: Priority score (0.0-1.0, higher = more important)
        created_at: When question was queued
        context: Additional context (original query, uncertainty score, etc.)
        attempts: How many times we tried to ask
        last_attempt: When we last tried to ask
    """
    question_id: str
    question_text: str
    conversation_id: str
    user_id: str
    priority: float
    created_at: str  # ISO format
    context: Dict
    attempts: int = 0
    last_attempt: Optional[str] = None


class QuestionQueue:
    """
    Redis-based queue for pending clarification questions.
    
    Features:
    - Priority-based retrieval (most important first)
    - Cooldown enforcement (prevents spam)
    - Automatic expiration (24 hours)
    - Deduplication (same question type per conversation)
    
    Example:
        queue = QuestionQueue(redis_url="redis://localhost:6380")
        await queue.initialize()
        
        # Queue a question
        await queue.add_question(
            question_text="Which system?",
            conversation_id="conv_123",
            priority=0.8,
            context={"uncertainty": 0.6}
        )
        
        # Get next question (if timing is good)
        question = await queue.get_next_question(
            conversation_id="conv_123",
            cooldown_seconds=60
        )
        
        if question:
            print(question.question_text)
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6380",
        cooldown_seconds: int = 60,
        max_attempts: int = 3,
        expiry_hours: int = 24
    ):
        """
        Initialize question queue.
        
        Args:
            redis_url: Redis connection URL (default: cognitive Redis from Phase 1)
            cooldown_seconds: Minimum seconds between questions (default: 60)
            max_attempts: Max times to try asking before giving up (default: 3)
            expiry_hours: Hours until question expires (default: 24)
        """
        self.redis_url = redis_url
        self.cooldown_seconds = cooldown_seconds
        self.max_attempts = max_attempts
        self.expiry_hours = expiry_hours
        self.redis_client: Optional[aioredis.Redis] = None
        
        logger.info(
            "question_queue_initialized",
            cooldown_seconds=cooldown_seconds,
            max_attempts=max_attempts,
            expiry_hours=expiry_hours
        )
    
    async def initialize(self):
        """Connect to Redis."""
        try:
            self.redis_client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self.redis_client.ping()
            logger.info("question_queue_connected", redis_url=self.redis_url)
        except Exception as e:
            logger.error("question_queue_connection_failed", error=str(e))
            raise
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.debug("question_queue_closed")
    
    async def add_question(
        self,
        question_text: str,
        conversation_id: str,
        user_id: str = "unknown",
        priority: float = 0.5,
        context: Optional[Dict] = None
    ) -> str:
        """
        Add question to queue.
        
        Args:
            question_text: The question to ask
            conversation_id: Conversation identifier
            user_id: User identifier
            priority: Priority score (0.0-1.0, default 0.5)
            context: Additional context dict
            
        Returns:
            Question ID
        """
        
        if not self.redis_client:
            raise RuntimeError("Queue not initialized. Call initialize() first.")
        
        # Generate question ID
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        question_id = f"q_{conversation_id}_{timestamp}"
        
        # Check for duplicate (same question type in conversation)
        duplicate = await self._check_duplicate(conversation_id, question_text)
        if duplicate:
            logger.debug(
                "question_duplicate_skipped",
                conversation_id=conversation_id,
                question_preview=question_text[:50]
            )
            return duplicate
        
        # Create question object
        question = PendingQuestion(
            question_id=question_id,
            question_text=question_text,
            conversation_id=conversation_id,
            user_id=user_id,
            priority=priority,
            created_at=datetime.now().isoformat(),
            context=context or {},
            attempts=0
        )
        
        # Store in Redis
        key = self._get_question_key(question_id)
        value = json.dumps(asdict(question))
        
        # Set with expiry
        expiry_seconds = self.expiry_hours * 3600
        await self.redis_client.setex(key, expiry_seconds, value)
        
        # Add to priority queue (sorted set by priority)
        queue_key = self._get_queue_key(conversation_id)
        await self.redis_client.zadd(queue_key, {question_id: priority})
        
        # Set queue expiry too
        await self.redis_client.expire(queue_key, expiry_seconds)
        
        logger.info(
            "question_queued",
            question_id=question_id,
            conversation_id=conversation_id,
            priority=priority,
            question_preview=question_text[:50]
        )
        
        return question_id
    
    async def get_next_question(
        self,
        conversation_id: str,
        user_id: str = "unknown"
    ) -> Optional[PendingQuestion]:
        """
        Get next question from queue if timing is appropriate.
        
        Checks:
        1. Cooldown period (enough time since last question)
        2. Priority order (highest priority first)
        3. Max attempts (give up after 3 tries)
        
        Args:
            conversation_id: Conversation identifier
            user_id: User identifier for logging
            
        Returns:
            PendingQuestion if available, None otherwise
        """
        
        if not self.redis_client:
            raise RuntimeError("Queue not initialized. Call initialize() first.")
        
        # Check cooldown
        if not await self._check_cooldown(conversation_id):
            logger.debug(
                "question_cooldown_active",
                conversation_id=conversation_id,
                cooldown_seconds=self.cooldown_seconds
            )
            return None
        
        # Get highest priority question
        queue_key = self._get_queue_key(conversation_id)
        
        # ZREVRANGE gets highest score first (reverse order)
        results = await self.redis_client.zrevrange(queue_key, 0, 0)
        
        if not results:
            logger.debug("question_queue_empty", conversation_id=conversation_id)
            return None
        
        question_id = results[0]
        
        # Retrieve full question
        question_key = self._get_question_key(question_id)
        question_json = await self.redis_client.get(question_key)
        
        if not question_json:
            # Question expired, remove from queue
            await self.redis_client.zrem(queue_key, question_id)
            logger.debug("question_expired", question_id=question_id)
            return None
        
        question_data = json.loads(question_json)
        question = PendingQuestion(**question_data)
        
        # Check max attempts
        if question.attempts >= self.max_attempts:
            # Give up, remove from queue
            await self._remove_question(question_id, conversation_id)
            logger.info(
                "question_max_attempts_reached",
                question_id=question_id,
                attempts=question.attempts
            )
            return None
        
        # Update attempt tracking
        question.attempts += 1
        question.last_attempt = datetime.now().isoformat()
        
        # Save updated question
        await self.redis_client.setex(
            question_key,
            self.expiry_hours * 3600,
            json.dumps(asdict(question))
        )
        
        # Record cooldown
        await self._record_cooldown(conversation_id)
        
        # Remove from queue (will be re-added if not actually asked)
        await self.redis_client.zrem(queue_key, question_id)
        
        logger.info(
            "question_retrieved",
            question_id=question_id,
            conversation_id=conversation_id,
            priority=question.priority,
            attempt=question.attempts,
            user_id=user_id
        )
        
        return question
    
    async def mark_question_asked(
        self,
        question_id: str,
        conversation_id: str
    ):
        """
        Mark question as successfully asked (removes from queue).
        
        Args:
            question_id: Question identifier
            conversation_id: Conversation identifier
        """
        await self._remove_question(question_id, conversation_id)
        logger.info("question_marked_asked", question_id=question_id)
    
    async def requeue_question(
        self,
        question: PendingQuestion
    ):
        """
        Re-add question to queue (if not asked).
        
        Args:
            question: Question to re-queue
        """
        if question.attempts >= self.max_attempts:
            logger.debug("question_not_requeued_max_attempts", question_id=question.question_id)
            return
        
        queue_key = self._get_queue_key(question.conversation_id)
        await self.redis_client.zadd(queue_key, {question.question_id: question.priority})
        
        logger.debug("question_requeued", question_id=question.question_id)
    
    async def get_queue_stats(
        self,
        conversation_id: str
    ) -> Dict:
        """
        Get statistics about conversation's question queue.
        
        Returns:
            Dict with count, highest_priority, oldest_question
        """
        queue_key = self._get_queue_key(conversation_id)
        
        # Get count
        count = await self.redis_client.zcard(queue_key)
        
        if count == 0:
            return {"count": 0}
        
        # Get highest priority
        highest = await self.redis_client.zrevrange(queue_key, 0, 0, withscores=True)
        highest_priority = highest[0][1] if highest else 0.0
        
        # Get oldest (first in queue)
        oldest_id = await self.redis_client.zrange(queue_key, 0, 0)
        
        stats = {
            "count": count,
            "highest_priority": highest_priority,
            "oldest_question_id": oldest_id[0] if oldest_id else None
        }
        
        return stats
    
    async def clear_conversation_queue(
        self,
        conversation_id: str
    ):
        """Clear all questions for a conversation."""
        queue_key = self._get_queue_key(conversation_id)
        
        # Get all question IDs
        question_ids = await self.redis_client.zrange(queue_key, 0, -1)
        
        # Delete each question
        for qid in question_ids:
            await self.redis_client.delete(self._get_question_key(qid))
        
        # Delete queue
        await self.redis_client.delete(queue_key)
        
        logger.info("conversation_queue_cleared", conversation_id=conversation_id, count=len(question_ids))
    
    # Private helper methods
    
    def _get_question_key(self, question_id: str) -> str:
        """Get Redis key for question data."""
        return f"veda:curiosity:question:{question_id}"
    
    def _get_queue_key(self, conversation_id: str) -> str:
        """Get Redis key for conversation's question queue."""
        return f"veda:curiosity:queue:{conversation_id}"
    
    def _get_cooldown_key(self, conversation_id: str) -> str:
        """Get Redis key for cooldown tracking."""
        return f"veda:curiosity:cooldown:{conversation_id}"
    
    async def _check_duplicate(
        self,
        conversation_id: str,
        question_text: str
    ) -> Optional[str]:
        """Check if similar question already queued."""
        queue_key = self._get_queue_key(conversation_id)
        question_ids = await self.redis_client.zrange(queue_key, 0, -1)
        
        # Simple duplicate check (exact text match)
        for qid in question_ids:
            q_key = self._get_question_key(qid)
            q_json = await self.redis_client.get(q_key)
            if q_json:
                q_data = json.loads(q_json)
                if q_data.get("question_text") == question_text:
                    return qid
        
        return None
    
    async def _check_cooldown(self, conversation_id: str) -> bool:
        """Check if cooldown period has passed."""
        cooldown_key = self._get_cooldown_key(conversation_id)
        exists = await self.redis_client.exists(cooldown_key)
        return not exists  # True if cooldown expired
    
    async def _record_cooldown(self, conversation_id: str):
        """Record that a question was asked (start cooldown)."""
        cooldown_key = self._get_cooldown_key(conversation_id)
        await self.redis_client.setex(cooldown_key, self.cooldown_seconds, "1")
    
    async def _remove_question(self, question_id: str, conversation_id: str):
        """Remove question from queue and storage."""
        # Remove from queue
        queue_key = self._get_queue_key(conversation_id)
        await self.redis_client.zrem(queue_key, question_id)
        
        # Remove question data
        question_key = self._get_question_key(question_id)
        await self.redis_client.delete(question_key)
