"""
Veda Phase 4: Uncertainty Scorer
Pattern-based uncertainty detection using linguistic analysis.

NO LLM REQUIRED - uses pure pattern matching for:
- Query ambiguity detection
- Response hedging markers
- Missing context indicators
- Vague reference detection

Returns confidence scores to drive curiosity-driven clarifications.
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class UncertaintyResult:
    """
    Result of uncertainty analysis.
    
    Attributes:
        uncertainty_score: 0.0 (certain) to 1.0 (very uncertain)
        confidence_score: Inverse of uncertainty (for clarity)
        uncertainty_reasons: List of detected uncertainty signals
        should_ask_clarification: Whether to ask a question
        suggested_question: Optional clarification question
        query_ambiguity: Score for query ambiguity (0.0-1.0)
        response_hedging: Score for response hedging (0.0-1.0)
        context_missing: Score for missing context (0.0-1.0)
    """
    uncertainty_score: float
    confidence_score: float
    uncertainty_reasons: List[str]
    should_ask_clarification: bool
    suggested_question: Optional[str]
    query_ambiguity: float
    response_hedging: float
    context_missing: float


class UncertaintyScorer:
    """
    Detects uncertainty using linguistic patterns.
    
    Three main signals:
    1. Query Ambiguity - Is the question vague or ambiguous?
    2. Response Hedging - Does the response use uncertain language?
    3. Missing Context - Are there vague references without antecedents?
    
    No LLM needed - pure pattern matching for fast, cost-free detection.
    """
    
    # Uncertainty markers in responses
    HEDGING_MARKERS = [
        # Epistemic uncertainty
        "maybe", "perhaps", "possibly", "probably", "might", "could be",
        "may be", "may not", "might not", "could", "would", "should",
        
        # Subjective uncertainty  
        "i think", "i believe", "i assume", "i guess", "in my opinion",
        "seems like", "appears to", "looks like",
        
        # Conditional uncertainty
        "depends on", "it depends", "varies", "it varies", "can vary",
        "if you", "unless you", "assuming", "provided that",
        
        # Qualification
        "generally", "typically", "usually", "often", "sometimes",
        "in most cases", "in some cases", "it's possible",
        
        # Explicit uncertainty
        "not sure", "unclear", "uncertain", "don't know", "can't say",
        "hard to say", "difficult to", "can't tell"
    ]
    
    # Ambiguous query patterns
    AMBIGUOUS_PATTERNS = [
        # Vague action verbs with vague objects
        r"^(check|fix|restart|configure|update|install|remove|delete|change)\s+(the|it|that|this|them)\s*$",
        r"^(show|display|list|get)\s+(me\s+)?(the|it|that|this|them)\s*$",
        
        # "Which" questions without specificity
        r"^which\s+(one|system|instance|server|database|application)\b(?!.*\b(prod|dev|qa|test|specific|name)\b)",
        
        # Status/help requests without context
        r"^(what('s| is)|how('s| is))\s+(the\s+)?(status|issue|problem|error)\s*[?\.]?\s*$",
        r"^(help|assist|support)\s+(me|with|on)\s+(this|that|it)\s*$",
        
        # Generic nouns without specification
        r"\b(the|this|that)\s+(system|server|instance|application|database|issue|error|problem)\b(?!.*\b(prod|dev|qa|specific|called|named)\b)",
        
        # Pronouns without clear antecedents (in short queries)
        r"^(it|this|that|these|those|they)\s+(is|are|was|were|has|have|does|do)\b",
    ]
    
    # Vague reference indicators
    VAGUE_REFERENCES = [
        r"\bit\b", r"\bthis\b", r"\bthat\b", r"\bthese\b", r"\bthose\b",
        r"\bthe thing\b", r"\bthe stuff\b", r"\bsomething\b"
    ]
    
    def __init__(
        self,
        uncertainty_threshold: float = 0.45,
        query_weight: float = 0.4,
        response_weight: float = 0.35,
        context_weight: float = 0.25
    ):
        """
        Initialize uncertainty scorer.
        
        Args:
            uncertainty_threshold: Score above this triggers clarification (default 0.45)
            query_weight: Weight for query ambiguity (default 0.4)
            response_weight: Weight for response hedging (default 0.35)
            context_weight: Weight for missing context (default 0.25)
        """
        self.uncertainty_threshold = uncertainty_threshold
        self.query_weight = query_weight
        self.response_weight = response_weight
        self.context_weight = context_weight
        
        logger.info(
            "uncertainty_scorer_initialized",
            threshold=uncertainty_threshold,
            weights={
                "query": query_weight,
                "response": response_weight,
                "context": context_weight
            }
        )
    
    def score_uncertainty(
        self,
        user_query: str,
        assistant_response: str,
        conversation_length: int = 0
    ) -> UncertaintyResult:
        """
        Score uncertainty based on query and response analysis.
        
        Args:
            user_query: User's question/message
            assistant_response: Veda's generated response
            conversation_length: Number of turns in conversation (affects context scoring)
            
        Returns:
            UncertaintyResult with scores and recommendations
        """
        
        reasons = []
        
        # Signal 1: Query ambiguity
        query_ambiguity = self._score_query_ambiguity(user_query)
        if query_ambiguity > 0.5:
            reasons.append(f"Ambiguous query (score: {query_ambiguity:.2f})")
        
        # Signal 2: Response hedging
        response_hedging = self._score_response_hedging(assistant_response)
        if response_hedging > 0.4:
            reasons.append(f"Response hedging detected (score: {response_hedging:.2f})")
        
        # Signal 3: Missing context
        context_missing = self._score_missing_context(user_query, conversation_length)
        if context_missing > 0.5:
            reasons.append(f"Missing context (score: {context_missing:.2f})")
        
        # Weighted combination
        uncertainty_score = (
            query_ambiguity * self.query_weight +
            response_hedging * self.response_weight +
            context_missing * self.context_weight
        )
        
        uncertainty_score = min(1.0, uncertainty_score)
        confidence_score = 1.0 - uncertainty_score
        
        # Decision
        should_ask = uncertainty_score >= self.uncertainty_threshold
        
        # Generate suggested question if needed
        suggested_question = None
        if should_ask:
            suggested_question = self._generate_clarification_question(
                user_query,
                query_ambiguity,
                context_missing
            )
        
        logger.debug(
            "uncertainty_scored",
            uncertainty=f"{uncertainty_score:.2f}",
            confidence=f"{confidence_score:.2f}",
            query_ambiguity=f"{query_ambiguity:.2f}",
            response_hedging=f"{response_hedging:.2f}",
            context_missing=f"{context_missing:.2f}",
            should_ask=should_ask,
            reasons_count=len(reasons)
        )
        
        return UncertaintyResult(
            uncertainty_score=uncertainty_score,
            confidence_score=confidence_score,
            uncertainty_reasons=reasons,
            should_ask_clarification=should_ask,
            suggested_question=suggested_question,
            query_ambiguity=query_ambiguity,
            response_hedging=response_hedging,
            context_missing=context_missing
        )
    
    def _score_query_ambiguity(self, query: str) -> float:
        """Score how ambiguous/vague the query is."""
        
        score = 0.0
        query_lower = query.lower().strip()
        word_count = len(query.split())
        
        # Check for ambiguous patterns (more aggressive)
        for pattern in self.AMBIGUOUS_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                score += 0.5  # Increased from 0.3
        
        # Check for vague references in short queries
        if word_count < 8:  # Short queries are more likely ambiguous with pronouns
            for vague_ref in self.VAGUE_REFERENCES:
                if re.search(vague_ref, query_lower, re.IGNORECASE):
                    score += 0.3  # Increased from 0.2
        
        # Generic action verbs without specifics (more aggressive)
        generic_actions = ["check", "fix", "help", "show", "do", "handle", "restart", "configure"]
        if any(action in query_lower.split()[:3] for action in generic_actions):
            # Only count if no specific details provided
            if word_count < 6:
                score += 0.4  # Increased from 0.2
        
        # Very short queries are inherently ambiguous
        if word_count <= 3:
            score += 0.3
        
        return min(1.0, score)
    
    def _score_response_hedging(self, response: str) -> float:
        """Score how much hedging/uncertainty language is in the response."""
        
        response_lower = response.lower()
        
        # Count hedging markers
        hedge_count = sum(
            1 for marker in self.HEDGING_MARKERS 
            if marker in response_lower
        )
        
        # Normalize by response length (markers per 100 words)
        word_count = len(response.split())
        if word_count == 0:
            return 0.0
        
        # More than 1 hedge per 50 words is significant
        hedging_ratio = (hedge_count / word_count) * 50
        
        # Cap at 1.0
        score = min(1.0, hedging_ratio * 0.3)
        
        return score
    
    def _score_missing_context(self, query: str, conversation_length: int) -> float:
        """Score whether query lacks necessary context."""
        
        score = 0.0
        query_lower = query.lower()
        
        # Pronoun without antecedent (worse in short conversations)
        pronouns = ["it", "this", "that", "these", "those", "them"]
        has_pronoun = any(f" {p} " in f" {query_lower} " for p in pronouns)
        
        if has_pronoun:
            if conversation_length < 2:
                # Early in conversation, pronouns likely lack antecedent
                score += 0.5
            else:
                # Later in conversation, more likely to have context
                score += 0.2
        
        # "The X" without specification
        if re.search(r"\bthe\s+(system|instance|server|error|issue|problem)\b", query_lower):
            # Check if there's any specification following it
            if not re.search(r"\b(called|named|for|on|in|at)\b", query_lower):
                score += 0.3
        
        return min(1.0, score)
    
    def _generate_clarification_question(
        self,
        query: str,
        query_ambiguity: float,
        context_missing: float
    ) -> str:
        """Generate a natural clarification question based on detected ambiguity."""
        
        query_lower = query.lower()
        
        # Pattern-based question generation
        
        # 1. Vague object references
        if re.search(r"^(check|fix|restart|configure)\s+(the|it|that|this)", query_lower):
            return "which_specific"
        
        # 2. System/instance ambiguity
        if re.search(r"\b(system|instance|server)\b", query_lower):
            if not re.search(r"\b(prod|dev|qa|test|specific)\b", query_lower):
                return "which_environment"
        
        # 3. Pronoun without context
        if context_missing > 0.4:
            if re.search(r"^(it|this|that)\b", query_lower):
                return "what_specifically"
        
        # 4. Generic "help" or "show"
        if re.search(r"^(help|show|display)\s", query_lower):
            return "what_aspect"
        
        # Default
        return "general_clarification"


# Convenience function
def check_uncertainty(
    query: str,
    response: str,
    conversation_length: int = 0,
    threshold: float = 0.45
) -> UncertaintyResult:
    """
    Quick uncertainty check.
    
    Usage:
        result = check_uncertainty(
            query="Check the system",
            response="I'll check ST06 for CPU and memory...",
            conversation_length=0
        )
        
        if result.should_ask_clarification:
            print(f"Uncertainty: {result.uncertainty_score:.2f}")
            print(f"Suggested question: {result.suggested_question}")
    """
    scorer = UncertaintyScorer(uncertainty_threshold=threshold)
    return scorer.score_uncertainty(query, response, conversation_length)
