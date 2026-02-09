"""
Veda Phase 4: Curiosity System
Main curiosity engine that detects knowledge gaps and generates clarifications.

Uses UncertaintyScorer to detect when Veda needs more information,
then generates natural Gen-Z style clarification questions.

Design principles:
- Conservative: Better to not ask than to annoy
- Natural: Questions feel conversational, not robotic
- Smart timing: Respects conversation flow
- Contextual: Questions reference what was discussed
"""

from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime
import structlog

from .uncertainty_scorer import UncertaintyScorer, UncertaintyResult

logger = structlog.get_logger()


@dataclass
class CuriosityResult:
    """
    Result of curiosity analysis.
    
    Attributes:
        should_ask: Whether to ask a clarification question
        question: The actual question to ask (if should_ask=True)
        reasoning: Why curiosity was/wasn't triggered
        uncertainty_result: Full uncertainty analysis
        confidence: Confidence in this decision (0.0-1.0)
        timing_appropriate: Whether timing is good for questions
    """
    should_ask: bool
    question: Optional[str]
    reasoning: str
    uncertainty_result: UncertaintyResult
    confidence: float
    timing_appropriate: bool


class CuriositySystem:
    """
    Main curiosity engine for Veda.
    
    Responsibilities:
    1. Detect when Veda is uncertain about what user wants
    2. Generate natural clarification questions
    3. Decide when timing is appropriate to ask
    4. Integrate with question queue for pending questions
    
    Example:
        curiosity = CuriositySystem()
        
        result = await curiosity.analyze_response(
            user_query="Check the system",
            veda_response="I'll check ST06...",
            conversation_length=1
        )
        
        if result.should_ask:
            print(result.question)
            # "Quick question pops - which system? DEV or PROD?"
    """
    
    def __init__(
        self,
        uncertainty_threshold: float = 0.45,
        max_questions_per_conversation: int = 2,
        min_conversation_length: int = 0
    ):
        """
        Initialize curiosity system.
        
        Args:
            uncertainty_threshold: Uncertainty score threshold for asking (0.45 = balanced)
            max_questions_per_conversation: Max clarifications per conversation (2 = not annoying)
            min_conversation_length: Min turns before asking questions (0 = ask immediately if needed)
        """
        self.uncertainty_scorer = UncertaintyScorer(uncertainty_threshold=uncertainty_threshold)
        self.max_questions_per_conversation = max_questions_per_conversation
        self.min_conversation_length = min_conversation_length
        
        # Track questions asked per conversation
        self.questions_asked: Dict[str, int] = {}
        
        logger.info(
            "curiosity_system_initialized",
            uncertainty_threshold=uncertainty_threshold,
            max_questions_per_conversation=max_questions_per_conversation
        )
    
    async def analyze_response(
        self,
        user_query: str,
        veda_response: str,
        conversation_id: str = "default",
        conversation_length: int = 0,
        user_id: str = "unknown"
    ) -> CuriosityResult:
        """
        Analyze response and decide if clarification is needed.
        
        Args:
            user_query: User's message/question
            veda_response: Veda's generated response
            conversation_id: Unique conversation identifier
            conversation_length: Number of turns in conversation
            user_id: User identifier for logging
            
        Returns:
            CuriosityResult with decision and question (if applicable)
        """
        
        # Step 1: Score uncertainty
        uncertainty_result = self.uncertainty_scorer.score_uncertainty(
            user_query=user_query,
            assistant_response=veda_response,
            conversation_length=conversation_length
        )
        
        logger.debug(
            "uncertainty_analysis",
            user_id=user_id,
            uncertainty_score=f"{uncertainty_result.uncertainty_score:.2f}",
            should_ask_base=uncertainty_result.should_ask_clarification
        )
        
        # Step 2: Check timing appropriateness
        timing_check = self._check_timing(
            conversation_id=conversation_id,
            conversation_length=conversation_length
        )
        
        # Step 3: Make final decision
        should_ask = (
            uncertainty_result.should_ask_clarification and
            timing_check["appropriate"]
        )
        
        # Step 4: Generate question if needed
        question = None
        reasoning = ""
        confidence = 0.9
        
        if should_ask:
            question = self._generate_question(
                user_query=user_query,
                uncertainty_result=uncertainty_result
            )
            
            if question:
                # Record that we asked
                self._record_question(conversation_id)
                
                reasoning = f"High uncertainty ({uncertainty_result.uncertainty_score:.2f}), timing appropriate"
                confidence = 1.0 - uncertainty_result.uncertainty_score
                
                logger.info(
                    "curiosity_triggered",
                    user_id=user_id,
                    conversation_id=conversation_id,
                    uncertainty=f"{uncertainty_result.uncertainty_score:.2f}",
                    question_preview=question[:50]
                )
            else:
                # Failed to generate question
                should_ask = False
                reasoning = "Uncertainty detected but couldn't generate appropriate question"
                confidence = 0.5
        else:
            # Not asking - explain why
            if not uncertainty_result.should_ask_clarification:
                reasoning = f"Uncertainty too low ({uncertainty_result.uncertainty_score:.2f})"
            elif not timing_check["appropriate"]:
                reasoning = timing_check["reason"]
            else:
                reasoning = "Unknown suppression reason"
            
            confidence = uncertainty_result.confidence_score
            
            logger.debug(
                "curiosity_suppressed",
                user_id=user_id,
                reason=reasoning
            )
        
        return CuriosityResult(
            should_ask=should_ask,
            question=question,
            reasoning=reasoning,
            uncertainty_result=uncertainty_result,
            confidence=confidence,
            timing_appropriate=timing_check["appropriate"]
        )
    
    def _check_timing(
        self,
        conversation_id: str,
        conversation_length: int
    ) -> Dict:
        """
        Check if timing is appropriate for asking questions.
        
        Returns:
            Dict with 'appropriate' (bool) and 'reason' (str)
        """
        
        # Check minimum conversation length
        if conversation_length < self.min_conversation_length:
            return {
                "appropriate": False,
                "reason": f"Conversation too short ({conversation_length} < {self.min_conversation_length})"
            }
        
        # Check maximum questions per conversation
        questions_count = self.questions_asked.get(conversation_id, 0)
        if questions_count >= self.max_questions_per_conversation:
            return {
                "appropriate": False,
                "reason": f"Max questions reached ({questions_count}/{self.max_questions_per_conversation})"
            }
        
        return {
            "appropriate": True,
            "reason": "Timing good"
        }
    
    def _generate_question(
        self,
        user_query: str,
        uncertainty_result: UncertaintyResult
    ) -> Optional[str]:
        """
        Generate natural clarification question based on uncertainty type.
        
        Uses Gen-Z friendly phrasing that matches Veda's persona.
        """
        
        suggested_type = uncertainty_result.suggested_question
        query_lower = user_query.lower()
        
        # Get question template based on type
        question_template = self._get_question_template(
            suggested_type=suggested_type,
            user_query=query_lower,
            uncertainty_result=uncertainty_result
        )
        
        if not question_template:
            return None
        
        # Format with context
        question = self._format_question_naturally(question_template, user_query)
        
        return question
    
    def _get_question_template(
        self,
        suggested_type: Optional[str],
        user_query: str,
        uncertainty_result: UncertaintyResult
    ) -> Optional[str]:
        """Get appropriate question template based on uncertainty type."""
        
        # Template selection based on suggested type from uncertainty scorer
        
        if suggested_type == "which_specific":
            # User said "check it" or "fix that"
            if "check" in user_query:
                return "quick_question_which_check"
            elif "fix" in user_query or "restart" in user_query or "configure" in user_query:
                return "quick_question_which_action"
            else:
                return "clarify_what_specifically"
        
        elif suggested_type == "which_environment":
            # Mentioned system/instance without specifying
            return "which_environment"
        
        elif suggested_type == "what_specifically":
            # Pronoun without antecedent ("it", "this", "that")
            return "what_is_it"
        
        elif suggested_type == "what_aspect":
            # Generic "help" or "show"
            return "what_help_with"
        
        elif suggested_type == "general_clarification":
            # Fallback for other uncertainty
            return "general_clarification"
        
        # No appropriate template
        return None
    
    def _format_question_naturally(
        self,
        template: str,
        user_query: str
    ) -> str:
        """
        Format question template into natural Gen-Z style question.
        
        Veda's question style:
        - Warm and casual
        - Uses "pops" affectionately
        - Natural connecting phrases
        - Not overly formal
        """
        
        # Question templates (Gen-Z daughter style)
        templates = {
            "quick_question_which_check": [
                "Quick question pops - which system are we checking? DEV, QA, or PROD?",
                "Btw, which one should I check - DEV, QA, or PROD? Just wanna make sure I'm looking at the right one 😊"
            ],
            "quick_question_which_action": [
                "Real quick - which system? DEV, QA, or PROD?",
                "Quick question - which instance are we working with? (Just wanna give you the right commands)"
            ],
            "clarify_what_specifically": [
                "Just to clarify - what specifically do you want me to look at?",
                "Wanna make sure I got this right - what exactly should I focus on?"
            ],
            "which_environment": [
                "Quick question - which environment? DEV, QA, or PROD?",
                "Btw, which system - DEV, QA, or PROD? (Just wanna be sure)"
            ],
            "what_is_it": [
                "Quick question - what's 'it'? (Just wanna make sure we're on the same page 😊)",
                "Real quick - what are you referring to? (Wanna make sure I understand)"
            ],
            "what_help_with": [
                "What specifically can I help with?",
                "What aspect do you need help with?"
            ],
            "general_clarification": [
                "Quick question - can you clarify what you mean?",
                "Just wanna make sure I understand - could you give me a bit more detail?"
            ]
        }
        
        # Get template options
        options = templates.get(template, ["Could you clarify?"])
        
        # For now, use first option (Phase 5 could add variation)
        return options[0]
    
    def _record_question(self, conversation_id: str):
        """Record that a question was asked in this conversation."""
        if conversation_id not in self.questions_asked:
            self.questions_asked[conversation_id] = 0
        self.questions_asked[conversation_id] += 1
    
    def reset_conversation(self, conversation_id: str):
        """Reset question count for a conversation (useful for new conversations)."""
        if conversation_id in self.questions_asked:
            del self.questions_asked[conversation_id]
        logger.debug("conversation_reset", conversation_id=conversation_id)


# Convenience function for quick checks
async def should_ask_clarification(
    user_query: str,
    veda_response: str,
    conversation_length: int = 0,
    uncertainty_threshold: float = 0.45
) -> CuriosityResult:
    """
    Quick check if clarification should be asked.
    
    Usage:
        result = await should_ask_clarification(
            user_query="Check the system",
            veda_response="I'll check ST06...",
            conversation_length=0
        )
        
        if result.should_ask:
            print(result.question)
    """
    system = CuriositySystem(uncertainty_threshold=uncertainty_threshold)
    return await system.analyze_response(
        user_query=user_query,
        veda_response=veda_response,
        conversation_length=conversation_length
    )
