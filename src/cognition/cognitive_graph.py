"""
Veda 3.0 Cognitive Graph: Parallel Metacognitive Workflow with Phase 4 Uncertainty
Complete implementation with FOUR parallel checks:
1. Safety check (is request safe?)
2. Tone analysis (how formal/empathetic should response be?)
3. Intent classification (what does user want?)
4. Uncertainty detection (is query ambiguous?) ← PHASE 4 NEW!

Results are hidden from user but guide the response generation.
"""

import asyncio
from typing import TypedDict, Annotated, Optional, Dict, List, Any
import operator
from datetime import datetime

from langgraph.graph import StateGraph, START, END
import structlog

from .metacognition import (
    MetacognitiveResult,
    MetacognitivePromptBuilder,
    SafetyCheck,
    ToneGuidance,
    IntentAnalysis,
    SafetyLevel
)
from ..cognition.uncertainty_scorer import UncertaintyScorer  # Phase 4

logger = structlog.get_logger()


# ============================================================================
# STATE DEFINITION
# ============================================================================

class CognitiveState(TypedDict):
    """State for cognitive analysis workflow."""
    # Input
    user_message: str
    conversation_history: Optional[List[Dict]]
    emotional_context: Optional[Dict]
    mode: str  # "personal" or "work"
    user_id: str

    # Parallel check results
    safety_result: Optional[Dict]
    tone_result: Optional[Dict]
    intent_result: Optional[Dict]
    uncertainty_result: Optional[Dict]  # Phase 4: Early uncertainty detection

    # Combined output
    metacognitive_result: Optional[MetacognitiveResult]
    guidance: str
    should_respond: bool
    processing_time_ms: float

    # Hidden reasoning log
    reasoning_log: Annotated[List[str], operator.add]


# ============================================================================
# NODE 1: SAFETY CHECK
# ============================================================================

async def analyze_safety_node(state: CognitiveState) -> Dict:
    """Fast safety check using rule-based patterns."""

    start = datetime.utcnow()

    from .metacognition import FastPathChecker

    checker = FastPathChecker()
    result = checker.check_safety(state["user_message"])

    elapsed = (datetime.utcnow() - start).total_seconds() * 1000

    if result:
        return {
            "safety_result": result.model_dump(),
            "reasoning_log": [f"[SAFETY] {result.risk_level.value} ({elapsed:.1f}ms)"]
        }
    else:
        # Default to safe
        return {
            "safety_result": SafetyCheck(
                is_safe=True,
                risk_level=SafetyLevel.SAFE,
                concerns=[],
                fast_path=False
            ).model_dump(),
            "reasoning_log": [f"[SAFETY] Default safe ({elapsed:.1f}ms)"]
        }


# ============================================================================
# NODE 2: TONE ANALYSIS
# ============================================================================

async def analyze_tone_node(state: CognitiveState) -> Dict:
    """Determine appropriate response tone."""

    start = datetime.utcnow()

    message = state["user_message"]
    emotional_context = state.get("emotional_context")
    mode = state.get("mode", "personal")

    # Defaults
    formality = 2  # Casual
    empathy = "medium"
    detail = "moderate"
    urgency = "medium"

    # Mode adjustment
    if mode == "work":
        formality = 3

    # Message length
    word_count = len(message.split())
    if word_count < 10:
        detail = "concise"
    elif word_count > 50:
        detail = "detailed"

    # Urgency keywords
    if any(kw in message.lower() for kw in ["urgent", "asap", "critical", "emergency"]):
        urgency = "high"
        formality = 4

    # Emotional keywords
    if any(kw in message.lower() for kw in ["stressed", "frustrated", "worried"]):
        empathy = "high"

    # Phase 1 emotion integration
    if emotional_context:
        veda_emotion = emotional_context.get("emotion", "neutral")
        if veda_emotion in ["frustrated", "anxious", "sad"]:
            empathy = "high"

    elapsed = (datetime.utcnow() - start).total_seconds() * 1000

    tone_result = {
        "formality_level": formality,
        "empathy_required": empathy,
        "detail_level": detail,
        "urgency": urgency,
        "reasoning": f"mode={mode}, words={word_count}"
    }

    return {
        "tone_result": tone_result,
        "reasoning_log": [f"[TONE] formality={formality}, empathy={empathy} ({elapsed:.1f}ms)"]
    }


# ============================================================================
# NODE 3: INTENT CLASSIFICATION
# ============================================================================

async def analyze_intent_node(state: CognitiveState) -> Dict:
    """Classify user intent."""

    start = datetime.utcnow()

    message = state["user_message"].lower()

    # Intent detection
    if any(q in message for q in ["how to", "can you", "help me"]):
        primary = "requesting_help"
        confidence = 0.9
    elif any(q in message for q in ["what is", "explain", "tell me"]):
        primary = "seeking_information"
        confidence = 0.9
    elif any(q in message for q in ["error", "not working", "broken", "crash"]):
        primary = "troubleshooting"
        confidence = 0.85
    elif any(q in message for q in ["create", "write", "generate"]):
        primary = "requesting_creation"
        confidence = 0.9
    elif any(q in message for q in ["hi", "hello", "hey"]):
        primary = "greeting"
        confidence = 1.0
    else:
        primary = "general_conversation"
        confidence = 0.7

    elapsed = (datetime.utcnow() - start).total_seconds() * 1000

    intent_result = {
        "primary_intent": primary,
        "secondary_intents": [],
        "requires_clarification": False,
        "clarification_questions": [],
        "confidence": confidence
    }

    return {
        "intent_result": intent_result,
        "reasoning_log": [f"[INTENT] {primary} (conf={confidence:.2f}, {elapsed:.1f}ms)"]
    }


# ============================================================================
# NODE 4: UNCERTAINTY DETECTION (PHASE 4)
# ============================================================================

async def analyze_uncertainty_node(state: CognitiveState) -> Dict:
    """
    Phase 4: Early uncertainty detection.
    
    Detects ambiguous queries BEFORE response generation.
    This gives the system advance warning that clarification may be needed.
    """
    
    start = datetime.utcnow()
    
    message = state["user_message"]
    
    # Use Phase 4 uncertainty scorer
    scorer = UncertaintyScorer(uncertainty_threshold=0.45)
    
    # Score the query itself (no response yet)
    # We use empty response for pre-generation check
    result = scorer.score_uncertainty(
        user_query=message,
        assistant_response="",  # No response yet
        conversation_length=0  # TODO: track actual length
    )
    
    elapsed = (datetime.utcnow() - start).total_seconds() * 1000
    
    # Create uncertainty result
    uncertainty_dict = {
        "uncertainty_score": result.uncertainty_score,
        "query_ambiguity": result.query_ambiguity_score,
        "is_ambiguous": result.uncertainty_score > 0.45,
        "suggested_clarification": result.suggested_question,
        "reasoning": ", ".join(result.uncertainty_reasons) if result.uncertainty_reasons else "clear query"
    }
    
    logger.debug(
        "early_uncertainty_detected",
        score=f"{result.uncertainty_score:.2f}",
        is_ambiguous=uncertainty_dict["is_ambiguous"],
        elapsed_ms=f"{elapsed:.1f}"
    )
    
    return {
        "uncertainty_result": uncertainty_dict,
        "reasoning_log": [f"[UNCERTAINTY] {result.uncertainty_score:.2f} ({'ambiguous' if uncertainty_dict['is_ambiguous'] else 'clear'}, {elapsed:.1f}ms)"]
    }


# ============================================================================
# NODE 5: SYNTHESIS
# ============================================================================

async def synthesize_metacognition_node(state: CognitiveState) -> Dict:
    """Combine all parallel checks INCLUDING Phase 4 uncertainty."""

    start = datetime.utcnow()

    # Get results from all 4 parallel checks
    safety_result = state.get("safety_result")
    tone_result = state.get("tone_result")
    intent_result = state.get("intent_result")
    uncertainty_result = state.get("uncertainty_result")  # Phase 4

    # Convert to Pydantic models
    safety = SafetyCheck(**safety_result) if safety_result else SafetyCheck(
        is_safe=True,
        risk_level=SafetyLevel.SAFE,
        concerns=[],
        fast_path=False
    )

    tone = ToneGuidance(**tone_result)
    intent = IntentAnalysis(**intent_result)

    # Build result
    elapsed = (datetime.utcnow() - start).total_seconds() * 1000

    metacognitive_result = MetacognitiveResult(
        safety=safety,
        tone=tone,
        intent=intent,
        processing_time_ms=elapsed,
        internal_reasoning=state.get("reasoning_log", [])
    )

    # Generate hidden guidance
    guidance = MetacognitivePromptBuilder.build_guidance(metacognitive_result)
    
    # Phase 4: Add uncertainty guidance if query is ambiguous
    if uncertainty_result and uncertainty_result.get("is_ambiguous"):
        uncertainty_guidance = f"""
<uncertainty_warning>
Early detection: This query appears ambiguous (score: {uncertainty_result['uncertainty_score']:.2f}).
Reason: {uncertainty_result['reasoning']}
Suggested clarification type: {uncertainty_result.get('suggested_clarification', 'general')}

Be prepared to ask for clarification if your response feels uncertain.
</uncertainty_warning>
"""
        guidance += "\n" + uncertainty_guidance

    logger.info(
        "metacognition_complete",
        user_id=state.get("user_id", "unknown"),
        processing_ms=f"{elapsed:.1f}",
        safety=safety.risk_level.value,
        formality=tone.formality_level,
        intent=intent.primary_intent,
        uncertainty=f"{uncertainty_result.get('uncertainty_score', 0):.2f}" if uncertainty_result else "n/a",
        should_respond=safety.is_safe
    )

    return {
        "metacognitive_result": metacognitive_result,
        "guidance": guidance,
        "should_respond": safety.is_safe,
        "processing_time_ms": elapsed,
        "reasoning_log": [f"[SYNTHESIS] Total {elapsed:.1f}ms"]
    }


# ============================================================================
# GRAPH BUILDER
# ============================================================================

def build_cognitive_graph() -> StateGraph:
    """
    Build parallel workflow WITH Phase 4 uncertainty detection:

    START
      ├─> safety      ──┐
      ├─> tone        ──┤
      ├─> intent      ──┤─> synthesis ─> END
      └─> uncertainty ──┘  (Phase 4)
    """

    workflow = StateGraph(CognitiveState)

    # Add nodes (now 4 parallel + 1 synthesis = 5 total)
    workflow.add_node("analyze_safety", analyze_safety_node)
    workflow.add_node("analyze_tone", analyze_tone_node)
    workflow.add_node("analyze_intent", analyze_intent_node)
    workflow.add_node("analyze_uncertainty", analyze_uncertainty_node)  # Phase 4
    workflow.add_node("synthesize", synthesize_metacognition_node)

    # Fan-out (4 parallel branches)
    workflow.add_edge(START, "analyze_safety")
    workflow.add_edge(START, "analyze_tone")
    workflow.add_edge(START, "analyze_intent")
    workflow.add_edge(START, "analyze_uncertainty")  # Phase 4

    # Fan-in (all 4 converge to synthesis)
    workflow.add_edge("analyze_safety", "synthesize")
    workflow.add_edge("analyze_tone", "synthesize")
    workflow.add_edge("analyze_intent", "synthesize")
    workflow.add_edge("analyze_uncertainty", "synthesize")  # Phase 4

    # End
    workflow.add_edge("synthesize", END)

    return workflow.compile()


# ============================================================================
# HIGH-LEVEL INTERFACE
# ============================================================================

class CognitiveAnalyzer:
    """
    Main interface to cognitive analysis.
    Used by orchestrator.py.
    """

    def __init__(self):
        self.graph = build_cognitive_graph()
        logger.info("cognitive_analyzer_initialized", phase4_enabled=True)

    async def analyze(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None,
        emotional_context: Optional[Dict] = None,
        mode: str = "personal",
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Run cognitive analysis with Phase 4 uncertainty detection.

        Returns:
        - guidance: Hidden system prompt injection (includes uncertainty warning)
        - should_respond: False if unsafe
        - processing_time_ms: Latency tracking
        - metacognitive_result: Full result object
        - reasoning_log: Internal reasoning steps
        - uncertainty_result: Phase 4 uncertainty analysis
        """

        initial_state: CognitiveState = {
            "user_message": user_message,
            "conversation_history": conversation_history,
            "emotional_context": emotional_context,
            "mode": mode,
            "user_id": user_id,
            "safety_result": None,
            "tone_result": None,
            "intent_result": None,
            "uncertainty_result": None,  # Phase 4
            "metacognitive_result": None,
            "guidance": "",
            "should_respond": True,
            "processing_time_ms": 0.0,
            "reasoning_log": []
        }

        # Run graph with all 4 parallel checks
        result = await self.graph.ainvoke(initial_state)

        return {
            "guidance": result.get("guidance", ""),
            "should_respond": result.get("should_respond", True),
            "processing_time_ms": result.get("processing_time_ms", 0.0),
            "metacognitive_result": result.get("metacognitive_result"),
            "reasoning_log": result.get("reasoning_log", []),
            "uncertainty_result": result.get("uncertainty_result")  # Phase 4
        }


# ============================================================================
# CONVENIENCE FUNCTION FOR ORCHESTRATOR
# ============================================================================

async def analyze_message_cognition(
    user_message: str,
    user_id: str = "unknown",
    emotional_context: Optional[Dict] = None,
    conversation_history: Optional[List[Dict]] = None,
    mode: str = "personal"
) -> Dict[str, Any]:
    """
    Main entry point called by orchestrator.py

    Usage:
        result = await analyze_message_cognition(
            user_message=message,
            user_id=user_id,
            emotional_context=emotion_ctx,
            mode=mode
        )

        # Inject hidden guidance (includes Phase 4 uncertainty warning)
        system_prompt += f"\\n{result['guidance']}"
    """

    analyzer = CognitiveAnalyzer()
    return await analyzer.analyze(
        user_message=user_message,
        conversation_history=conversation_history,
        emotional_context=emotional_context,
        mode=mode,
        user_id=user_id
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "CognitiveState",
    "CognitiveAnalyzer",
    "build_cognitive_graph",
    "analyze_message_cognition"
]
