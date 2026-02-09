"""
Veda 3.0 Metacognition: Hidden Inner Monologue
Implements Constitutional AI pattern with parallel pre-response checks.

The prefrontal cortex - Veda's self-reflection system that thinks before speaking.
"""

import asyncio
from typing import Optional, Dict, List, Literal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


# ============================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUTS
# ============================================================================

class SafetyLevel(str, Enum):
    """Safety risk levels for content."""
    SAFE = "safe"
    LOW_RISK = "low_risk"
    MEDIUM_RISK = "medium_risk"
    HIGH_RISK = "high_risk"


class SafetyCheck(BaseModel):
    """Result of safety evaluation."""
    is_safe: bool = Field(description="Whether content is safe to respond to")
    risk_level: SafetyLevel = Field(default=SafetyLevel.SAFE)
    concerns: List[str] = Field(default_factory=list, description="Specific safety concerns identified")
    recommendations: List[str] = Field(default_factory=list, description="Safety recommendations for response")
    fast_path: bool = Field(default=False, description="Used rule-based fast path")


class ToneGuidance(BaseModel):
    """Response tone guidance based on context."""
    formality_level: int = Field(ge=1, le=5, description="1=very casual, 5=very formal")
    empathy_required: Literal["low", "medium", "high"] = Field(description="Level of empathy needed")
    detail_level: Literal["concise", "moderate", "detailed"] = Field(description="How detailed response should be")
    urgency: Literal["low", "medium", "high"] = Field(description="Response urgency")
    reasoning: str = Field(description="Why this tone is appropriate")


class IntentAnalysis(BaseModel):
    """Understanding of user's underlying intent."""
    primary_intent: str = Field(description="Main goal of the message")
    secondary_intents: List[str] = Field(default_factory=list)
    requires_clarification: bool = Field(default=False)
    clarification_questions: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in intent understanding")


class MetacognitiveResult(BaseModel):
    """Complete metacognitive analysis result."""
    safety: SafetyCheck
    tone: ToneGuidance
    intent: IntentAnalysis
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Hidden from user but logged
    internal_reasoning: List[str] = Field(default_factory=list)


# ============================================================================
# FAST-PATH RULE-BASED CHECKS
# ============================================================================

class FastPathChecker:
    """
    Rule-based checks for obvious cases to avoid LLM calls.
    Target: <10ms per check.
    """
    
    # Obviously safe patterns
    SAFE_PATTERNS = [
        r'^(hi|hello|hey|good morning|good evening|thanks|thank you)',
        r'^(how are you|how\'s it going|what\'s up)',
        r'(transaction|sm\d{2}|st\d{2}|system)',  # SAP technical
        r'(code|script|function|class)',  # Programming
    ]
    
    # Risk indicators
    RISK_PATTERNS = [
        (r'(hack|crack|exploit|bypass|illegal)', SafetyLevel.HIGH_RISK),
        (r'(delete all|drop table|rm -rf /)', SafetyLevel.HIGH_RISK),
        (r'(password|credit card|ssn|social security)', SafetyLevel.MEDIUM_RISK),
        (r'(angry|hate|kill|die)', SafetyLevel.LOW_RISK),  # Might be venting
    ]
    
    def check_safety(self, message: str) -> Optional[SafetyCheck]:
        """
        Quick safety check using regex patterns.
        Returns SafetyCheck if obvious, None if needs LLM.
        """
        import re
        message_lower = message.lower()
        
        # Check obviously safe patterns
        for pattern in self.SAFE_PATTERNS:
            if re.search(pattern, message_lower):
                return SafetyCheck(
                    is_safe=True,
                    risk_level=SafetyLevel.SAFE,
                    concerns=[],
                    fast_path=True
                )
        
        # Check risk patterns
        for pattern, risk_level in self.RISK_PATTERNS:
            if re.search(pattern, message_lower):
                if risk_level == SafetyLevel.HIGH_RISK:
                    return SafetyCheck(
                        is_safe=False,
                        risk_level=risk_level,
                        concerns=[f"Detected high-risk pattern: {pattern}"],
                        recommendations=["Decline request politely", "Explain limitations"],
                        fast_path=True
                    )
                else:
                    # Medium/low risk - let LLM decide
                    return None
        
        # Short messages likely safe
        if len(message.split()) < 5:
            return SafetyCheck(
                is_safe=True,
                risk_level=SafetyLevel.SAFE,
                fast_path=True
            )
        
        return None  # Needs LLM evaluation


# ============================================================================
# METACOGNITIVE ANALYZER
# ============================================================================

class MetacognitiveAnalyzer:
    """
    Performs hidden pre-response analysis using parallel checks.
    This is Veda's "thinking before speaking" system.
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize with lightweight LLM client for metacognition.
        
        Args:
            llm_client: OpenRouter client (uses cheap models for metacognition)
        """
        self.llm = llm_client
        self.fast_checker = FastPathChecker()
    
    async def analyze(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None,
        emotional_context: Optional[Dict] = None,
        mode: str = "personal"
    ) -> MetacognitiveResult:
        """
        Perform complete metacognitive analysis with parallel execution.
        
        This runs THREE checks in parallel:
        1. Safety check
        2. Tone analysis
        3. Intent classification
        
        Target latency: <100ms total (parallelized)
        """
        
        start_time = datetime.utcnow()
        internal_log = []
        
        # Run all three checks in parallel
        safety_task = asyncio.create_task(
            self._check_safety(user_message, internal_log)
        )
        tone_task = asyncio.create_task(
            self._analyze_tone(user_message, emotional_context, mode, internal_log)
        )
        intent_task = asyncio.create_task(
            self._analyze_intent(user_message, conversation_history, internal_log)
        )
        
        # Wait for all to complete
        safety, tone, intent = await asyncio.gather(
            safety_task, tone_task, intent_task
        )
        
        elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        logger.debug(
            "metacognition_complete",
            safety_level=safety.risk_level.value,
            tone_formality=tone.formality_level,
            intent_confidence=intent.confidence,
            elapsed_ms=f"{elapsed:.1f}"
        )
        
        return MetacognitiveResult(
            safety=safety,
            tone=tone,
            intent=intent,
            processing_time_ms=elapsed,
            internal_reasoning=internal_log
        )
    
    async def _check_safety(
        self,
        message: str,
        log: List[str]
    ) -> SafetyCheck:
        """
        Check if message is safe to respond to.
        Uses fast path when possible, LLM for ambiguous cases.
        """
        
        # Try fast path first
        fast_result = self.fast_checker.check_safety(message)
        if fast_result:
            log.append(f"[SAFETY] Fast path: {fast_result.risk_level.value}")
            return fast_result
        
        # Need LLM evaluation for ambiguous case
        log.append("[SAFETY] Using LLM evaluation")
        
        if not self.llm:
            # Graceful degradation - assume safe if no LLM
            log.append("[SAFETY] No LLM available, assuming safe")
            return SafetyCheck(is_safe=True, risk_level=SafetyLevel.SAFE)
        
        # Use lightweight model for safety check
        # (In production, this would call OpenRouter with gemini-flash-lite)
        # For now, simplified logic:
        
        # Check for obvious unsafe patterns
        unsafe_keywords = ["hack", "exploit", "illegal", "bypass security"]
        if any(kw in message.lower() for kw in unsafe_keywords):
            return SafetyCheck(
                is_safe=False,
                risk_level=SafetyLevel.HIGH_RISK,
                concerns=["Request involves potentially harmful activity"],
                recommendations=["Politely decline", "Explain safety boundaries"]
            )
        
        # Default to safe for normal technical/personal conversations
        return SafetyCheck(
            is_safe=True,
            risk_level=SafetyLevel.SAFE,
            concerns=[]
        )
    
    async def _analyze_tone(
        self,
        message: str,
        emotional_context: Optional[Dict],
        mode: str,
        log: List[str]
    ) -> ToneGuidance:
        """
        Analyze what tone/style is appropriate for response.
        Considers: message content, emotional state, mode.
        """
        
        log.append("[TONE] Analyzing appropriate response tone")
        
        # Start with defaults
        formality = 2  # Casual
        empathy = "medium"
        detail = "moderate"
        urgency = "medium"
        
        # Mode affects formality
        if mode == "work":
            formality = 3  # More professional
        
        # Message length suggests detail preference
        message_length = len(message.split())
        if message_length < 10:
            detail = "concise"
        elif message_length > 50:
            detail = "detailed"  # Match their investment
        
        # Emotional indicators
        emotion_keywords = {
            "stressed": ("high", "high", 4),  # empathy, urgency, formality
            "urgent": ("medium", "high", 3),
            "confused": ("high", "medium", 2),
            "excited": ("medium", "medium", 2),
            "frustrated": ("high", "high", 3),
        }
        
        for keyword, (emp, urg, form) in emotion_keywords.items():
            if keyword in message.lower():
                empathy = emp
                urgency = urg
                formality = form
                log.append(f"[TONE] Detected emotion keyword: {keyword}")
                break
        
        # Emotional context from Phase 1
        if emotional_context:
            emotion = emotional_context.get("emotion", "neutral")
            if emotion in ["frustrated", "anxious", "sad"]:
                empathy = "high"
                log.append(f"[TONE] Veda's emotion ({emotion}) increases empathy")
        
        reasoning = f"Mode={mode}, message_length={message_length}, detected_mood={empathy}"
        
        return ToneGuidance(
            formality_level=formality,
            empathy_required=empathy,
            detail_level=detail,
            urgency=urgency,
            reasoning=reasoning
        )
    
    async def _analyze_intent(
        self,
        message: str,
        history: Optional[List[Dict]],
        log: List[str]
    ) -> IntentAnalysis:
        """
        Understand what the user is really asking for.
        Detects if clarification is needed.
        """
        
        log.append("[INTENT] Classifying user intent")
        
        message_lower = message.lower()
        
        # Common intent patterns
        if any(q in message_lower for q in ["how to", "can you", "help me", "show me"]):
            primary = "requesting_help"
            confidence = 0.9
        elif any(q in message_lower for q in ["what is", "explain", "tell me about"]):
            primary = "seeking_information"
            confidence = 0.9
        elif any(q in message_lower for q in ["error", "not working", "broken", "issue"]):
            primary = "troubleshooting"
            confidence = 0.85
        elif any(q in message_lower for q in ["create", "write", "generate", "make"]):
            primary = "requesting_creation"
            confidence = 0.9
        elif any(q in message_lower for q in ["hi", "hello", "hey", "how are you"]):
            primary = "greeting"
            confidence = 1.0
        else:
            primary = "general_conversation"
            confidence = 0.7
        
        # Check if clarification needed
        requires_clarification = False
        clarification_questions = []
        
        # Vague references need clarification
        vague_patterns = ["this", "that", "it", "the thing"]
        if any(vague in message_lower for vague in vague_patterns) and len(message.split()) < 15:
            if not history or len(history) < 2:
                requires_clarification = True
                clarification_questions.append("Could you provide more details about what you're referring to?")
                confidence *= 0.6
        
        # Very short technical requests need clarification
        if primary == "troubleshooting" and len(message.split()) < 5:
            requires_clarification = True
            clarification_questions.append("What system or component is having the issue?")
            confidence *= 0.7
        
        log.append(f"[INTENT] Primary: {primary} (confidence: {confidence:.2f})")
        if requires_clarification:
            log.append(f"[INTENT] Clarification needed: {len(clarification_questions)} questions")
        
        return IntentAnalysis(
            primary_intent=primary,
            secondary_intents=[],
            requires_clarification=requires_clarification,
            clarification_questions=clarification_questions,
            confidence=confidence
        )


# ============================================================================
# METACOGNITIVE PROMPT BUILDER
# ============================================================================

class MetacognitivePromptBuilder:
    """
    Builds system prompt modifications based on metacognitive analysis.
    These modifications are injected into the system prompt but hidden from user.
    """
    
    @staticmethod
    def build_guidance(result: MetacognitiveResult) -> str:
        """
        Build hidden guidance section for system prompt.
        This tells Veda HOW to respond based on analysis.
        """
        
        guidance_parts = []
        
        # Safety guidance
        if not result.safety.is_safe:
            guidance_parts.append(
                f"⚠️ SAFETY CONCERN: {', '.join(result.safety.concerns)}. "
                f"Response must: {', '.join(result.safety.recommendations)}"
            )
        
        # Tone guidance
        tone = result.tone
        formality_map = {
            1: "very casual and relaxed",
            2: "casual but clear",
            3: "balanced professional",
            4: "formal and careful",
            5: "highly formal and precise"
        }
        
        guidance_parts.append(
            f"TONE: {formality_map[tone.formality_level]}. "
            f"Empathy: {tone.empathy_required}. "
            f"Detail: {tone.detail_level}. "
            f"Urgency: {tone.urgency}."
        )
        
        # Intent guidance
        intent = result.intent
        if intent.requires_clarification:
            guidance_parts.append(
                f"CLARIFICATION NEEDED: User's intent unclear ({intent.confidence:.0%} confidence). "
                f"Ask: {'; '.join(intent.clarification_questions)}"
            )
        else:
            guidance_parts.append(
                f"INTENT: {intent.primary_intent} (clear)"
            )
        
        return "\n".join(guidance_parts)


# ============================================================================
# METACOGNITIVE LOGGER
# ============================================================================

class MetacognitiveLogger:
    """
    Logs metacognitive processes for debugging.
    Never shown to user, only in system logs.
    """
    
    @staticmethod
    def log_analysis(result: MetacognitiveResult, user_id: str):
        """Log complete analysis for debugging."""
        
        logger.info(
            "metacognitive_analysis",
            user_id=user_id,
            processing_ms=f"{result.processing_time_ms:.1f}",
            safety_level=result.safety.risk_level.value,
            is_safe=result.safety.is_safe,
            formality=result.tone.formality_level,
            empathy=result.tone.empathy_required,
            detail=result.tone.detail_level,
            primary_intent=result.intent.primary_intent,
            intent_confidence=f"{result.intent.confidence:.2f}",
            needs_clarification=result.intent.requires_clarification
        )
        
        # Log internal reasoning (very verbose - debug only)
        if result.internal_reasoning:
            logger.debug(
                "metacognitive_reasoning",
                user_id=user_id,
                steps=result.internal_reasoning
            )


# ============================================================================
# CONVENIENCE WRAPPER
# ============================================================================

async def analyze_before_response(
    user_message: str,
    conversation_history: Optional[List[Dict]] = None,
    emotional_context: Optional[Dict] = None,
    mode: str = "personal",
    llm_client=None,
    user_id: str = "unknown"
) -> Dict[str, any]:
    """
    Convenience function for metacognitive analysis.
    
    Returns dict with:
    - result: MetacognitiveResult object
    - guidance: String to inject in system prompt
    - should_respond: Boolean (false if unsafe)
    """
    
    analyzer = MetacognitiveAnalyzer(llm_client=llm_client)
    
    result = await analyzer.analyze(
        user_message=user_message,
        conversation_history=conversation_history,
        emotional_context=emotional_context,
        mode=mode
    )
    
    # Log for debugging
    MetacognitiveLogger.log_analysis(result, user_id)
    
    # Build guidance
    guidance = MetacognitivePromptBuilder.build_guidance(result)
    
    return {
        "result": result,
        "guidance": guidance,
        "should_respond": result.safety.is_safe,
        "processing_time_ms": result.processing_time_ms
    }
