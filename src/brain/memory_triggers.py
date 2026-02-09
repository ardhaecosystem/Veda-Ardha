"""
Veda Phase 3: Memory Trigger Detection
Determines when to run associative memory retrieval.

Philosophy: Veda should naturally recall related memories, not spam every message.
Triggers on:
- Follow-up questions
- Topic shifts with context
- Conversation gaps
- Complex queries
NOT on:
- Simple greetings
- One-word replies
- Rapid back-and-forth
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class TriggerDecision:
    """
    Result of trigger detection.
    
    Attributes:
        should_trigger: Whether to run associative retrieval
        reason: Why trigger was/wasn't activated
        confidence: 0.0-1.0 confidence in this decision
        context_hints: Additional context for retrieval (if triggered)
    """
    should_trigger: bool
    reason: str
    confidence: float
    context_hints: Dict[str, any]


class TriggerDetector:
    """
    Detects when associative memory should be triggered.
    
    Uses multiple signals:
    1. Message patterns (follow-ups, topic shifts)
    2. Conversation flow (gaps, continuity)
    3. Query complexity (depth of question)
    4. Time-based heuristics (rate limiting)
    
    Design principles:
    - Conservative by default (avoid spam)
    - Context-aware (understand conversation flow)
    - Adaptive (learns from user patterns)
    """
    
    def __init__(
        self,
        min_message_length: int = 15,
        max_triggers_per_conversation: int = 3,
        min_seconds_between_triggers: int = 30,
        topic_shift_threshold: float = 0.4
    ):
        """
        Initialize trigger detector.
        
        Args:
            min_message_length: Min words to consider for associations
            max_triggers_per_conversation: Rate limit per conversation
            min_seconds_between_triggers: Cooldown between associations
            topic_shift_threshold: How different topics must be to trigger
        """
        self.min_message_length = min_message_length
        self.max_triggers_per_conversation = max_triggers_per_conversation
        self.min_seconds_between_triggers = min_seconds_between_triggers
        self.topic_shift_threshold = topic_shift_threshold
        
        # Track trigger history (in-memory for now)
        self.trigger_history: Dict[str, List[datetime]] = {}
        
        logger.info(
            "trigger_detector_initialized",
            min_message_length=min_message_length,
            max_triggers_per_conversation=max_triggers_per_conversation
        )
    
    def should_trigger_associations(
        self,
        current_message: str,
        conversation_history: Optional[List[Dict]] = None,
        user_id: str = "default",
        has_direct_memories: bool = False
    ) -> TriggerDecision:
        """
        Decide whether to trigger associative memory retrieval.
        
        Args:
            current_message: User's current message
            conversation_history: Recent conversation context
            user_id: User identifier for rate limiting
            has_direct_memories: Whether direct memory search found results
            
        Returns:
            TriggerDecision with reasoning
        """
        
        # Initialize context hints
        context_hints = {
            "message_type": "unknown",
            "conversation_depth": 0,
            "topic_continuity": "unknown"
        }
        
        # Signal 1: Check rate limiting
        rate_limit_check = self._check_rate_limits(user_id)
        if not rate_limit_check["allowed"]:
            return TriggerDecision(
                should_trigger=False,
                reason=rate_limit_check["reason"],
                confidence=1.0,
                context_hints=context_hints
            )
        
        # Signal 2: Message quality checks
        quality_check = self._check_message_quality(current_message)
        if not quality_check["passes"]:
            return TriggerDecision(
                should_trigger=False,
                reason=quality_check["reason"],
                confidence=0.9,
                context_hints=context_hints
            )
        
        context_hints["message_type"] = quality_check.get("message_type", "unknown")
        
        # Signal 3: Conversation flow analysis
        flow_analysis = self._analyze_conversation_flow(
            current_message,
            conversation_history
        )
        context_hints.update(flow_analysis)
        
        # Signal 4: Pattern matching for trigger phrases
        pattern_match = self._match_trigger_patterns(current_message)
        
        # Signal 5: Memory availability check
        if not has_direct_memories:
            return TriggerDecision(
                should_trigger=False,
                reason="no_direct_memories_to_associate_from",
                confidence=1.0,
                context_hints=context_hints
            )
        
        # Decision logic: Combine signals
        should_trigger, reason, confidence = self._make_trigger_decision(
            quality_check,
            flow_analysis,
            pattern_match
        )
        
        # Record trigger if activated
        if should_trigger:
            self._record_trigger(user_id)
            logger.info(
                "association_triggered",
                user_id=user_id,
                reason=reason,
                confidence=confidence
            )
        else:
            logger.debug(
                "association_skipped",
                user_id=user_id,
                reason=reason
            )
        
        return TriggerDecision(
            should_trigger=should_trigger,
            reason=reason,
            confidence=confidence,
            context_hints=context_hints
        )
    
    def _check_rate_limits(self, user_id: str) -> Dict:
        """Check if user has hit rate limits."""
        
        now = datetime.now()
        
        # Get user's trigger history
        if user_id not in self.trigger_history:
            self.trigger_history[user_id] = []
        
        history = self.trigger_history[user_id]
        
        # Clean old entries (older than 1 hour)
        history = [t for t in history if (now - t).seconds < 3600]
        self.trigger_history[user_id] = history
        
        # Check max triggers per conversation
        if len(history) >= self.max_triggers_per_conversation:
            return {
                "allowed": False,
                "reason": "max_triggers_per_conversation_reached"
            }
        
        # Check minimum time between triggers
        if history:
            last_trigger = history[-1]
            seconds_since = (now - last_trigger).seconds
            if seconds_since < self.min_seconds_between_triggers:
                return {
                    "allowed": False,
                    "reason": f"cooldown_active_{self.min_seconds_between_triggers - seconds_since}s_remaining"
                }
        
        return {"allowed": True}
    
    def _check_message_quality(self, message: str) -> Dict:
        """Check if message quality warrants associations."""
        
        message_lower = message.lower().strip()
        words = message_lower.split()
        word_count = len(words)
        
        # Too short
        if word_count < 3:
            return {
                "passes": False,
                "reason": "message_too_short",
                "message_type": "brief"
            }
        
        # Simple greetings
        greetings = ["hi", "hey", "hello", "good morning", "good evening"]
        if word_count <= 3 and any(g in message_lower for g in greetings):
            return {
                "passes": False,
                "reason": "simple_greeting",
                "message_type": "greeting"
            }
        
        # One-word replies
        affirmations = ["ok", "okay", "yes", "no", "sure", "thanks", "thank you", "cool", "nice"]
        if word_count <= 2 and message_lower in affirmations:
            return {
                "passes": False,
                "reason": "one_word_reply",
                "message_type": "affirmation"
            }
        
        # Determine message type
        message_type = "unknown"
        if "?" in message:
            message_type = "question"
        elif any(cmd in message_lower for cmd in ["explain", "help", "show me", "tell me"]):
            message_type = "request"
        elif any(tech in message_lower for tech in ["sap", "system", "error", "code", "database"]):
            message_type = "technical"
        else:
            message_type = "conversational"
        
        return {
            "passes": True,
            "word_count": word_count,
            "message_type": message_type
        }
    
    def _analyze_conversation_flow(
        self,
        current_message: str,
        conversation_history: Optional[List[Dict]]
    ) -> Dict:
        """Analyze conversation flow to detect natural moments for associations."""
        
        if not conversation_history:
            return {
                "conversation_depth": 0,
                "topic_continuity": "new_conversation",
                "has_topic_shift": False
            }
        
        depth = len(conversation_history)
        
        # Detect topic shift (simple keyword overlap)
        if depth > 0:
            last_message = conversation_history[-1].get("content", "")
            current_words = set(current_message.lower().split())
            last_words = set(last_message.lower().split())
            
            # Remove common words
            stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
            current_words -= stop_words
            last_words -= stop_words
            
            if current_words and last_words:
                overlap = len(current_words & last_words)
                continuity = overlap / max(len(current_words), len(last_words))
                
                has_shift = continuity < self.topic_shift_threshold
                
                return {
                    "conversation_depth": depth,
                    "topic_continuity": f"{continuity:.2f}",
                    "has_topic_shift": has_shift
                }
        
        return {
            "conversation_depth": depth,
            "topic_continuity": "unknown",
            "has_topic_shift": False
        }
    
    def _match_trigger_patterns(self, message: str) -> Dict:
        """Match message against patterns that suggest associations would be helpful."""
        
        message_lower = message.lower()
        
        # Pattern 1: Follow-up questions
        follow_up_patterns = [
            "related to", "similar to", "like that", "like this",
            "what about", "how about", "also", "and what",
            "remember when", "last time", "before"
        ]
        
        has_follow_up = any(pattern in message_lower for pattern in follow_up_patterns)
        
        # Pattern 2: Comparison requests
        comparison_patterns = [
            "compare", "difference between", "vs", "versus",
            "better than", "worse than", "similar", "same as"
        ]
        
        has_comparison = any(pattern in message_lower for pattern in comparison_patterns)
        
        # Pattern 3: Context references
        context_patterns = [
            "that we discussed", "we talked about", "you mentioned",
            "earlier you said", "from before", "previously"
        ]
        
        has_context_ref = any(pattern in message_lower for pattern in context_patterns)
        
        # Pattern 4: "Remind me" style
        reminder_patterns = [
            "remind me", "what was", "what did", "do you remember"
        ]
        
        has_reminder = any(pattern in message_lower for pattern in reminder_patterns)
        
        return {
            "has_follow_up": has_follow_up,
            "has_comparison": has_comparison,
            "has_context_ref": has_context_ref,
            "has_reminder": has_reminder,
            "pattern_score": sum([has_follow_up, has_comparison, has_context_ref, has_reminder]) / 4.0
        }
    
    def _make_trigger_decision(
        self,
        quality_check: Dict,
        flow_analysis: Dict,
        pattern_match: Dict
    ) -> tuple[bool, str, float]:
        """
        Combine all signals to make final trigger decision.
        
        Returns:
            (should_trigger, reason, confidence)
        """
        
        # Strong YES signals
        if pattern_match["has_context_ref"] or pattern_match["has_reminder"]:
            return (True, "explicit_context_reference", 0.95)
        
        if pattern_match["has_comparison"] and quality_check.get("message_type") == "question":
            return (True, "comparison_request", 0.85)
        
        # Moderate YES signals
        if flow_analysis.get("has_topic_shift") and quality_check.get("word_count", 0) > 10:
            return (True, "topic_shift_with_depth", 0.75)
        
        if pattern_match["has_follow_up"] and flow_analysis.get("conversation_depth", 0) > 2:
            return (True, "follow_up_in_deep_conversation", 0.70)
        
        # Technical questions often benefit from context
        if quality_check.get("message_type") == "technical" and quality_check.get("word_count", 0) >= 12:
            return (True, "complex_technical_question", 0.65)
        
        # Pattern score threshold
        if pattern_match["pattern_score"] >= 0.5:
            return (True, "pattern_match_threshold", 0.60)
        
        # Default: Don't trigger
        return (False, "no_strong_trigger_signal", 0.8)
    
    def _record_trigger(self, user_id: str):
        """Record that a trigger was activated."""
        if user_id not in self.trigger_history:
            self.trigger_history[user_id] = []
        
        self.trigger_history[user_id].append(datetime.now())
    
    def reset_user_history(self, user_id: str):
        """Reset trigger history for a user (useful for new conversations)."""
        if user_id in self.trigger_history:
            del self.trigger_history[user_id]
        logger.debug("trigger_history_reset", user_id=user_id)


# Convenience function for orchestrator
def should_run_associations(
    message: str,
    conversation_history: Optional[List[Dict]] = None,
    user_id: str = "default",
    has_direct_memories: bool = False
) -> TriggerDecision:
    """
    Quick check if associations should run.
    
    Usage in orchestrator:
        trigger = should_run_associations(
            message=user_message,
            conversation_history=history,
            user_id=user_id,
            has_direct_memories=len(memories) > 0
        )
        
        if trigger.should_trigger:
            associations = await get_associations(...)
    """
    detector = TriggerDetector()
    return detector.should_trigger_associations(
        current_message=message,
        conversation_history=conversation_history,
        user_id=user_id,
        has_direct_memories=has_direct_memories
    )
