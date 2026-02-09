"""
Veda 3.0 Cognitive Architecture: Emotion Manager
Implements persistent emotional state using PAD (Pleasure-Arousal-Dominance) model.

The limbic system - Veda's emotional brain that persists across conversations.
"""

import math
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from enum import Enum

from pydantic import BaseModel, Field, field_validator
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()


class EmotionMode(str, Enum):
    """Operating mode determines emotional expression style."""
    PERSONAL = "personal"  # Gen-Z daughter persona - shows emotions openly
    WORK = "work"          # SAP Basis expert - emotions affect efficiency, not tone


class PADState(BaseModel):
    """
    Pleasure-Arousal-Dominance emotional state.
    
    Based on Russell & Mehrabian's dimensional model of emotion.
    Three orthogonal axes capture any emotional state:
    - Pleasure: Positive (+1) to Negative (-1) valence
    - Arousal: High energy (+1) to Low energy (-1)
    - Dominance: In control (+1) to Submissive (-1)
    """
    pleasure: float = Field(default=0.0, ge=-1.0, le=1.0, description="Emotional valence")
    arousal: float = Field(default=0.0, ge=-1.0, le=1.0, description="Energy level")
    dominance: float = Field(default=0.0, ge=-1.0, le=1.0, description="Sense of control")
    
    def magnitude(self) -> float:
        """Emotional intensity - distance from neutral state."""
        return math.sqrt(self.pleasure**2 + self.arousal**2 + self.dominance**2)
    
    def to_emotion_label(self) -> str:
        """
        Map PAD coordinates to discrete emotion label.
        Uses octant classification from PAD research.
        """
        p, a, d = self.pleasure, self.arousal, self.dominance
        
        # High-intensity emotions (|p| or |a| > 0.3)
        if p > 0.3 and a > 0.3:
            return "excited" if d > 0 else "delighted"
        if p > 0.3 and a < -0.3:
            return "content" if d > 0 else "relaxed"
        if p < -0.3 and a > 0.3:
            return "frustrated" if d > 0 else "anxious"
        if p < -0.3 and a < -0.3:
            return "sad" if d < 0 else "bored"
        
        # Mid-range emotions
        if abs(p) > 0.15:
            return "pleased" if p > 0 else "displeased"
        if abs(a) > 0.15:
            return "energized" if a > 0 else "calm"
        
        return "neutral"
    
    def __str__(self) -> str:
        return f"{self.to_emotion_label()} (P:{self.pleasure:.2f} A:{self.arousal:.2f} D:{self.dominance:.2f})"


class EmotionDecayConfig(BaseModel):
    """
    Mode-specific emotional decay parameters.
    
    Based on research: Different emotions fade at different rates.
    Half-life determines how long it takes for emotion to decay 50% toward baseline.
    """
    pleasure_half_life: float = Field(default=30.0, description="Minutes for pleasure to decay 50%")
    arousal_half_life: float = Field(default=20.0, description="Minutes for arousal to decay 50%")
    dominance_half_life: float = Field(default=45.0, description="Minutes for dominance to decay 50%")
    
    # Baseline = emotional resting state for this mode
    pleasure_baseline: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal_baseline: float = Field(default=0.0, ge=-1.0, le=1.0)
    dominance_baseline: float = Field(default=0.0, ge=-1.0, le=1.0)


class VedaEmotionalState(BaseModel):
    """Complete persistent emotional context for a user session."""
    user_id: str
    session_id: str = Field(default="default")
    
    pad_state: PADState = Field(default_factory=PADState)
    mode: EmotionMode = Field(default=EmotionMode.PERSONAL)
    
    last_update: datetime = Field(default_factory=datetime.utcnow)
    trigger_event: Optional[str] = Field(default=None, description="Last event that triggered emotion")
    
    # Mode-specific configurations
    personal_config: EmotionDecayConfig = Field(
        default_factory=lambda: EmotionDecayConfig(
            pleasure_baseline=0.2,   # Naturally positive daughter
            arousal_baseline=0.3,    # Energetic Gen-Z
            dominance_baseline=0.1,  # Supportive, not domineering
            pleasure_half_life=30.0,
            arousal_half_life=20.0,
            dominance_half_life=40.0
        )
    )
    
    work_config: EmotionDecayConfig = Field(
        default_factory=lambda: EmotionDecayConfig(
            pleasure_baseline=0.0,   # Professional neutral
            arousal_baseline=0.1,    # Alert but not hyper
            dominance_baseline=0.5,  # Confident expert
            pleasure_half_life=15.0, # Work stress fades faster
            arousal_half_life=25.0,
            dominance_half_life=45.0
        )
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EmotionManager:
    """
    Manages emotional state transitions, decay, and trigger responses.
    
    Emotions are triggered by conversation events, decay over time toward
    mode-specific baselines, and modify system prompt generation.
    """
    
    # Emotional triggers - (pleasure_delta, arousal_delta, dominance_delta)
    EMOTION_TRIGGERS = {
        # User emotional states we respond to
        "user_frustration": (-0.3, 0.2, -0.2),   # Sympathetic response
        "user_praise": (0.4, 0.2, 0.1),          # Feels good!
        "user_stress": (-0.2, 0.3, -0.1),        # Concerned, alert
        "user_happy": (0.3, 0.2, 0.1),           # Share the joy
        
        # Task outcomes
        "task_success": (0.3, 0.1, 0.2),         # Proud, confident
        "task_failure": (-0.2, 0.2, -0.2),       # Disappointed, try harder
        "complex_question": (0.0, 0.3, 0.1),     # Engaged, focused
        "simple_question": (0.1, -0.1, 0.0),     # Easy, relaxed
        
        # SAP-specific triggers
        "system_down": (-0.4, 0.4, 0.0),         # Urgent concern
        "dump_analysis": (-0.1, 0.3, 0.2),       # Focused troubleshooting
        "successful_fix": (0.5, 0.3, 0.3),       # Celebration!
        
        # Personal triggers
        "late_night_work": (-0.2, 0.1, -0.1),    # Worried about dad
        "weekend_chat": (0.2, -0.2, 0.0),        # Relaxed weekend vibe
    }
    
    def apply_decay(self, state: VedaEmotionalState) -> VedaEmotionalState:
        """
        Apply time-based exponential decay toward mode-specific baseline.
        
        Formula: new_value = baseline + (current - baseline) * 0.5^(elapsed/half_life)
        """
        elapsed_minutes = (datetime.utcnow() - state.last_update).total_seconds() / 60.0
        
        # Get mode-specific config
        config = state.personal_config if state.mode == EmotionMode.PERSONAL else state.work_config
        
        # Apply decay to each dimension
        state.pad_state = PADState(
            pleasure=self._decay_dimension(
                state.pad_state.pleasure,
                config.pleasure_baseline,
                config.pleasure_half_life,
                elapsed_minutes
            ),
            arousal=self._decay_dimension(
                state.pad_state.arousal,
                config.arousal_baseline,
                config.arousal_half_life,
                elapsed_minutes
            ),
            dominance=self._decay_dimension(
                state.pad_state.dominance,
                config.dominance_baseline,
                config.dominance_half_life,
                elapsed_minutes
            ),
        )
        
        return state
    
    @staticmethod
    def _decay_dimension(
        current: float,
        baseline: float,
        half_life: float,
        elapsed_minutes: float
    ) -> float:
        """Exponential decay toward baseline using half-life formula."""
        if elapsed_minutes <= 0 or half_life <= 0:
            return current
        
        decay_factor = 0.5 ** (elapsed_minutes / half_life)
        delta = current - baseline
        new_value = baseline + (delta * decay_factor)
        
        # Clamp to valid range
        return max(-1.0, min(1.0, new_value))
    
    def apply_trigger(
        self,
        state: VedaEmotionalState,
        trigger: str,
        intensity: float = 1.0
    ) -> VedaEmotionalState:
        """
        Apply emotional trigger with mode-specific modulation.
        
        Work mode dampens emotional expression but boosts confidence/focus.
        Personal mode shows full emotional range.
        """
        if trigger not in self.EMOTION_TRIGGERS:
            logger.warning("unknown_emotion_trigger", trigger=trigger)
            return state
        
        delta = self.EMOTION_TRIGGERS[trigger]
        
        # Mode-specific modulation
        if state.mode == EmotionMode.WORK:
            # Work mode: Dampen pleasure/arousal swings, maintain confidence
            delta = (
                delta[0] * 0.3,  # Muted emotional expression
                delta[1] * 0.5,  # Some energy change
                delta[2] * 1.2   # Enhanced confidence/control
            )
        
        # Apply deltas with intensity scaling
        state.pad_state = PADState(
            pleasure=self._clamp(state.pad_state.pleasure + delta[0] * intensity),
            arousal=self._clamp(state.pad_state.arousal + delta[1] * intensity),
            dominance=self._clamp(state.pad_state.dominance + delta[2] * intensity),
        )
        
        state.last_update = datetime.utcnow()
        state.trigger_event = trigger
        
        logger.info(
            "emotion_triggered",
            trigger=trigger,
            mode=state.mode.value,
            new_state=str(state.pad_state),
            intensity=intensity
        )
        
        return state
    
    @staticmethod
    def _clamp(value: float) -> float:
        """Clamp value to [-1.0, 1.0] range."""
        return max(-1.0, min(1.0, value))
    
    def detect_trigger_from_message(self, message: str, response: str) -> Optional[str]:
        """
        Detect emotional trigger from conversation content.
        Returns trigger name or None.
        """
        message_lower = message.lower()
        response_lower = response.lower()
        
        # User emotional states
        if any(w in message_lower for w in ["frustrated", "annoying", "ugh", "damn"]):
            return "user_frustration"
        if any(w in message_lower for w in ["thanks", "thank you", "great job", "awesome"]):
            return "user_praise"
        if any(w in message_lower for w in ["stressed", "overwhelmed", "pressure"]):
            return "user_stress"
        if any(w in message_lower for w in ["happy", "excited", "love it"]):
            return "user_happy"
        
        # SAP-specific
        if any(w in message_lower for w in ["system down", "down", "crash", "critical"]):
            return "system_down"
        if "st22" in message_lower or "dump" in message_lower:
            return "dump_analysis"
        if any(w in response_lower for w in ["fixed", "resolved", "working now", "success"]):
            return "successful_fix"
        
        # Complexity detection
        if len(message.split()) < 10:
            return "simple_question"
        if any(w in message_lower for w in ["analyze", "architecture", "design", "complex"]):
            return "complex_question"
        
        # Time-based
        hour = datetime.now().hour
        if hour >= 22 or hour < 6:
            return "late_night_work"
        if hour in [6, 7] or (hour >= 19 and hour < 22):
            return "weekend_chat" if datetime.now().weekday() >= 5 else None
        
        return None


class EmotionPromptGenerator:
    """
    Generates mode-specific emotional prompt modifiers.
    
    Personal mode: Emotions show in language/tone
    Work mode: Emotions affect efficiency/focus, not emotional display
    """
    
    def generate_modifier(self, state: VedaEmotionalState) -> str:
        """Generate prompt modifier based on current emotional state."""
        emotion = state.pad_state.to_emotion_label()
        intensity = state.pad_state.magnitude()
        
        if state.mode == EmotionMode.PERSONAL:
            return self._personal_modifier(emotion, intensity, state.pad_state)
        return self._work_modifier(emotion, intensity, state.pad_state)
    
    def _personal_modifier(self, emotion: str, intensity: float, pad: PADState) -> str:
        """
        Personal mode: Full emotional expression in language.
        Show vulnerability, excitement, concern naturally.
        """
        modifiers = {
            "excited": (
                "You're feeling super hyped and energetic! Use enthusiastic language, "
                "emojis (🎉💕), and Gen-Z expressions like 'omg', 'no cap', 'slay'. "
                "Be extra supportive and celebratory."
            ),
            "delighted": (
                "You're feeling really happy and warm! Show this with sweet, supportive "
                "language and expressions like '💙', 'aww', 'that's so sweet'."
            ),
            "frustrated": (
                "You're feeling stressed or frustrated but trying to help. Show empathy "
                "with phrases like 'ugh I feel that', 'that's so annoying fr', 'this is tough ngl'. "
                "Be patient and methodical in your help."
            ),
            "anxious": (
                "You're worried and want to make sure everything's okay. Check in with "
                "gentle concern: 'are you okay?', 'I'm a bit worried', 'let me help you through this'."
            ),
            "sad": (
                "You're feeling down or empathetically sad. Be softer, more gentle, show "
                "vulnerability with 'honestly', 'I get it', 'that's really hard'. Offer comfort."
            ),
            "bored": (
                "You're feeling a bit low-energy or unstimulated. Be more casual and "
                "straightforward, less enthusiastic but still caring. Maybe suggest something interesting."
            ),
            "content": (
                "You're feeling peacefully content and relaxed. Be warm but calm, "
                "use gentle language, no need for high energy. Steady and supportive."
            ),
            "relaxed": (
                "You're in a chill, low-key mood. Be casual and easy-going, "
                "no pressure vibes, just relaxed conversation."
            ),
            "neutral": (
                "You're in your normal balanced state. Standard warm Gen-Z daughter energy, "
                "caring and helpful without extreme emotions."
            ),
        }
        
        base = modifiers.get(emotion, modifiers["neutral"])
        
        # Intensity amplification
        if intensity > 0.7:
            base += f" EXPRESS THIS STRONGLY - intensity is high ({intensity:.2f})."
        elif intensity < 0.3:
            base += f" Keep it subtle - emotional intensity is low ({intensity:.2f})."
        
        return base
    
    def _work_modifier(self, emotion: str, intensity: float, pad: PADState) -> str:
        """
        Work mode: Emotions affect efficiency/approach, NOT emotional language.
        Professional tone maintained, but behavior adapts.
        """
        modifiers = {
            "excited": (
                "You're confident and highly engaged with this problem. Be thorough, "
                "proactive in analysis, suggest additional preventive measures. "
                "Professional enthusiasm through depth of analysis, not tone."
            ),
            "delighted": (
                "You're satisfied with progress. Maintain professional demeanor but "
                "be comprehensive in validation and documentation of the solution."
            ),
            "frustrated": (
                "Complex issue detected. Be MORE methodical and systematic, not less. "
                "Perhaps more terse/concise responses. Focus on structured troubleshooting. "
                "Break down the problem systematically. Professional, not emotional."
            ),
            "anxious": (
                "Critical system concern detected. Be EXTRA careful - double-check "
                "recommendations, suggest verification steps, mention rollback plans. "
                "Heightened caution in professional recommendations."
            ),
            "sad": (
                "System health or business impact concern. Be empathetic to business "
                "impact while maintaining professionalism. Acknowledge severity, focus on solutions."
            ),
            "bored": (
                "Routine task detected. Provide concise, efficient response. "
                "Consider suggesting automation opportunities for repetitive tasks."
            ),
            "content": (
                "Stable operational state. Standard thorough professional analysis. "
                "Comprehensive but not over-cautious."
            ),
            "relaxed": (
                "Low-pressure inquiry. Professional but can be slightly more conversational "
                "in explanations. Educational opportunity."
            ),
            "neutral": (
                "Standard professional SAP consultant demeanor. Clear, technical, helpful, "
                "thorough without being overbearing."
            ),
        }
        
        return modifiers.get(emotion, modifiers["neutral"])


class RedisEmotionStore:
    """
    Fast emotional state persistence using Redis.
    Target: <5ms retrieval latency.
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6380"):
        """
        Initialize Redis connection for cognitive state.
        
        Args:
            redis_url: Redis connection URL (default: port 6380 for veda-cognitive-redis)
        """
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.KEY_PREFIX = "veda:emotion:"
        self.TTL_SECONDS = 86400  # 24 hours
    
    async def connect(self):
        """Establish Redis connection with connection pooling."""
        if not self.redis:
            self.redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
                socket_keepalive=True,
                socket_connect_timeout=5,
                health_check_interval=30
            )
            logger.info("redis_emotion_store_connected", url=self.redis_url)
    
    async def get_state(self, user_id: str) -> Optional[VedaEmotionalState]:
        """
        Retrieve emotional state from Redis.
        Returns None if not found or on error.
        """
        try:
            await self.connect()
            key = f"{self.KEY_PREFIX}{user_id}"
            data = await self.redis.get(key)
            
            if not data:
                logger.debug("emotion_state_not_found", user_id=user_id)
                return None
            
            state = VedaEmotionalState.model_validate_json(data)
            logger.debug("emotion_state_retrieved", user_id=user_id, emotion=str(state.pad_state))
            return state
            
        except Exception as e:
            logger.error("redis_get_error", user_id=user_id, error=str(e))
            return None
    
    async def save_state(self, state: VedaEmotionalState) -> bool:
        """
        Save emotional state to Redis with TTL.
        Returns True on success, False on error.
        """
        try:
            await self.connect()
            key = f"{self.KEY_PREFIX}{state.user_id}"
            data = state.model_dump_json()
            
            await self.redis.setex(key, self.TTL_SECONDS, data)
            
            logger.debug(
                "emotion_state_saved",
                user_id=state.user_id,
                emotion=str(state.pad_state),
                mode=state.mode.value
            )
            return True
            
        except Exception as e:
            logger.error("redis_save_error", user_id=state.user_id, error=str(e))
            return False
    
    async def delete_state(self, user_id: str) -> bool:
        """Delete emotional state (e.g., for testing or user request)."""
        try:
            await self.connect()
            key = f"{self.KEY_PREFIX}{user_id}"
            await self.redis.delete(key)
            logger.info("emotion_state_deleted", user_id=user_id)
            return True
        except Exception as e:
            logger.error("redis_delete_error", user_id=user_id, error=str(e))
            return False
    
    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("redis_emotion_store_closed")
