"""
Veda 3.0 Orchestrator: Unified Persona + Cognitive Architecture
Phase 1: Emotion tracking ✅
Phase 2: Metacognition (hidden inner monologue) ✅
"""
import asyncio
from typing import TypedDict, Literal, Annotated, Optional, List, Union, Dict, Any
import operator
import re
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
import structlog

# IMPORTS
from .openrouter_client import OpenRouterClient
from ..persona.veda_persona import UnifiedVedaPersona, clean_code_blocks
from ..brain.memory_manager import MemoryManager
from ..eyes.search_tool import SearchTool
from ..optimization.token_optimizer import TokenOptimizer
from ..sap.diagnostic_workflow import SAPDiagnosticWorkflow

# VEDA 3.0: Cognitive Architecture (Phase 2)
from ..cognition.cognitive_graph import analyze_message_cognition
from ..brain.memory_triggers import should_run_associations
from ..cognition.curiosity_system import CuriositySystem
from ..cognition.question_queue import QuestionQueue

logger = structlog.get_logger()

class ConversationState(TypedDict):
    """State for conversation flow."""
    messages: Annotated[list[dict], operator.add]
    mode: Literal["personal", "work"]
    task_type: Literal["planning", "coding", "chat", "research"]
    persona_active: bool
    user_emotion: Optional[str]
    response: str
    memory_context: list[dict]
    search_results: Optional[str]

class VedaOrchestrator:
    def __init__(self, openrouter_client: OpenRouterClient, memory_manager: MemoryManager):
        self.client = openrouter_client
        self.memory = memory_manager

        # Initialize Components
        self.persona = UnifiedVedaPersona()
        self.search_tool = SearchTool()
        self.checkpointer = MemorySaver()
        self.optimizer = TokenOptimizer()
        self.sap_agent = SAPDiagnosticWorkflow()

        # Placeholder graph
        self.graph = self._build_graph()
        
        # VEDA 3.0: Cognitive features toggle
        self.cognitive_enabled = True  # Master switch for Phase 2 metacognition
        
        # Phase 4: Curiosity-Driven Learning
        self.curiosity_enabled = True
        self.curiosity = CuriositySystem(
            uncertainty_threshold=0.45,
            max_questions_per_conversation=2
        )
        self.question_queue = QuestionQueue(
            redis_url="redis://localhost:6380",
            cooldown_seconds=60
        )
        
        logger.info(
            "veda_3.0_orchestrator_initialized",
            cognitive_enabled=self.cognitive_enabled,
            features=["emotion", "metacognition", "vision", "sap_agent", "memory"]
        )

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(ConversationState)
        workflow.add_node("classify_mode", lambda state: {"mode": "personal"})
        workflow.add_edge(START, "classify_mode")
        workflow.add_edge("classify_mode", END)
        return workflow.compile(checkpointer=self.checkpointer)

    # --- MAIN OPEN-WEBUI ENTRY POINT ---
    async def process_message_streaming(
        self,
        message: str,
        thread_id: str,
        full_message_payload: Optional[List[Dict[str, Any]]] = None,
        emotional_context: Optional[Dict[str, Any]] = None,  # NEW: From api.py (Phase 1)
        user_id: str = "unknown"  # NEW: For cognitive logging
    ):
        """
        Veda 3.0: Processes message with Cognitive Architecture + Vision Support.
        
        NEW in 3.0:
        - emotional_context: Emotional state from Phase 1
        - Metacognitive analysis before response (Phase 2)
        - Hidden inner monologue logged but never shown to user
        
        'message' is text-only (for logic).
        'full_message_payload' is the raw list (for the Vision Model).
        """
        
        logger.info(
            "veda_3.0_request_started",
            user_id=user_id,
            message_length=len(message),
            has_vision=bool(full_message_payload),
            has_emotion=bool(emotional_context),
            cognitive_enabled=self.cognitive_enabled
        )

        # 1. PARALLEL MEMORY RETRIEVAL (Uses text 'message')
        personal_memories_task = self.memory.search(query=message, memory_type="personal", limit=3)
        work_memories_task = self.memory.search(query=message, memory_type="work", limit=3)
        personal_memories, work_memories = await asyncio.gather(personal_memories_task, work_memories_task)

        # 2. FORMAT & OPTIMIZE CONTEXT
        personal_context_raw = self._format_context(personal_memories, "Personal")
        work_context_raw = self._format_context(work_memories, "Work/SAP")

        # Compress
        personal_context = self.optimizer.compress_search_results(personal_context_raw, target_ratio=0.7)
        work_context = self.optimizer.compress_search_results(work_context_raw, target_ratio=0.7)

        # 3. PHASE 3: ASSOCIATIVE MEMORY RETRIEVAL
        associations_text = ""
        
        # Check if we should trigger associations
        trigger_decision = should_run_associations(
            message=message,
            conversation_history=None,  # TODO: pass actual history
            user_id=user_id,
            has_direct_memories=(len(personal_memories) > 0 or len(work_memories) > 0)
        )
        
        if trigger_decision.should_trigger:
            logger.info(
                "associative_memory_triggered",
                user_id=user_id,
                reason=trigger_decision.reason,
                confidence=trigger_decision.confidence
            )
            
            # Get associations
            associations = []
            
            # Personal associations
            if personal_memories:
                try:
                    personal_assocs = await self.memory.get_associated_memories(
                        query=message,
                        direct_memories=personal_memories,
                        memory_type="personal",
                        max_hops=2,
                        min_relevance=0.6
                    )
                    associations.extend(personal_assocs)
                except Exception as e:
                    logger.error("personal_associations_error", error=str(e))
            
            # Work associations
            if work_memories:
                try:
                    work_assocs = await self.memory.get_associated_memories(
                        query=message,
                        direct_memories=work_memories,
                        memory_type="work",
                        max_hops=2,
                        min_relevance=0.6
                    )
                    associations.extend(work_assocs)
                except Exception as e:
                    logger.error("work_associations_error", error=str(e))
            
            # Format for prompt
            if associations:
                associations_text = self._format_associations(associations)
                logger.info("associations_found", user_id=user_id, count=len(associations))
        else:
            logger.debug("associations_skipped", user_id=user_id, reason=trigger_decision.reason)


        # ====================================================================
        # VEDA 3.0: COGNITIVE ANALYSIS (Phase 2 - Metacognition)
        # ====================================================================
        
        metacognitive_guidance = ""
        should_respond = True
        
        if self.cognitive_enabled:
            try:
                logger.debug("running_cognitive_analysis", user_id=user_id)
                
                # Determine mode (simple heuristic for now)
                mode = self._detect_mode(message)
                
                # Run cognitive analysis (THREE checks in parallel!)
                # - Safety check
                # - Tone analysis
                # - Intent classification
                cognitive_result = await analyze_message_cognition(
                    user_message=message,
                    user_id=user_id,
                    emotional_context=emotional_context,
                    conversation_history=None,  # Future: pass actual history
                    mode=mode
                )
                
                metacognitive_guidance = cognitive_result.get("guidance", "")
                should_respond = cognitive_result.get("should_respond", True)
                processing_ms = cognitive_result.get("processing_time_ms", 0.0)
                
                logger.info(
                    "cognitive_analysis_complete",
                    user_id=user_id,
                    processing_ms=f"{processing_ms:.1f}",
                    should_respond=should_respond,
                    has_guidance=bool(metacognitive_guidance)
                )
                
                # If unsafe to respond, stop here with polite decline
                if not should_respond:
                    safety_response = (
                        "I appreciate you reaching out, but I need to respectfully "
                        "decline this request. Is there something else I can help you with? 💙"
                    )
                    yield safety_response
                    return
                
            except Exception as e:
                logger.error("cognitive_analysis_error", error=str(e), user_id=user_id)
                # Graceful degradation - continue without metacognition
                metacognitive_guidance = ""
                should_respond = True

        # 3. INTELLIGENCE LAYER (SAP Agent & Search)
        search_results = None

        # Check for Complex SAP Issues
        is_complex_sap = any(kw in message.lower() for kw in ["dump", "st22", "error", "fail", "crash", "performance"])

        # Agent Delegation (Only if NO image - Agents struggle with image passing currently)
        if is_complex_sap and not full_message_payload:
            logger.info("delegating_to_sap_agent", query=message[:50])
            agent_diagnosis = await self.sap_agent.run(message)
            search_results = f"AGENT DIAGNOSIS:\n{agent_diagnosis}"
            search_results = self.optimizer.compress_search_results(search_results, target_ratio=0.6)

        elif self._should_trigger_research(message):
            logger.info("triggering_standard_research", query=message[:50])
            category = "sap" if any(kw in message.lower() for kw in ["sap", "basis", "abap"]) else "it"
            search_results_raw = await self.search_tool.search(query=message, category=category, max_results=5)
            if search_results_raw:
                search_results = self.optimizer.compress_search_results(search_results_raw, target_ratio=0.5)

        # 4. BUILD UNIFIED PROMPT (WITH COGNITIVE INJECTION!)
        current_hour = datetime.now().hour
        
        # Base system prompt (from persona)
        system_prompt = self.persona.get_unified_system_prompt(
            personal_context=personal_context,
            work_context=work_context,
            user_emotion=None,  # Deprecated - now using emotional_context
            current_hour=current_hour,
            emotional_state=emotional_context,  # Phase 1 emotion integration
            associations_context=associations_text  # Phase 3 associative memory
        )
        
        # VEDA 3.0: Inject metacognitive guidance (HIDDEN from user!)
        if metacognitive_guidance:
            system_prompt += f"\n\n<metacognitive_guidance>\n{metacognitive_guidance}\n</metacognitive_guidance>"
            logger.debug(
                "metacognitive_guidance_injected",
                user_id=user_id,
                guidance_length=len(metacognitive_guidance)
            )
        
        # Add search results if available
        if search_results:
            system_prompt += f"\n\n<external_research>\n{search_results}\n</external_research>"

        # 5. CONSTRUCT MESSAGES FOR LLM
        # If we have an image payload, use it. Otherwise use text.
        user_content = full_message_payload if full_message_payload else message

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        # 6. ROUTE TO MODEL & VISION HANDLING
        task_type = "chat"

        # If image is present, prioritize Vision-Capable models
        if full_message_payload:
            # If requesting analysis/diagrams, use Claude (Planning)
            if any(p in message.lower() for p in ["analyze", "plan", "diagram", "architecture"]):
                task_type = "planning"
            # If requesting code from screenshot, Claude is also better
            elif "code" in message.lower() or "script" in message.lower():
                task_type = "planning"
            else:
                # Default to Gemini (Chat) which has native vision
                task_type = "chat"
        else:
            # Standard Text Routing
            if "code" in message.lower() or "script" in message.lower(): 
                task_type = "coding"
            elif any(p in message.lower() for p in ["analyze", "plan"]): 
                task_type = "planning"

        logger.info(
            "generating_response",
            task_type=task_type,
            has_image=bool(full_message_payload),
            has_cognitive_guidance=bool(metacognitive_guidance),
            has_emotion=bool(emotional_context)
        )

        # 7. STREAM RESPONSE WITH PHASE 4 CURIOSITY
        response_chunks = []
        async for chunk in await self.client.chat(
            messages=messages,
            task_type=task_type,
            stream=True,
            temperature=0.7
        ):
            response_chunks.append(chunk)
        
        full_response = "".join(response_chunks)
        
        # Phase 4: Uncertainty check and question injection
        final_response = full_response
        
        if self.curiosity_enabled:
            try:
                # Lazy initialize question queue on first use
                if not self.question_queue.redis_client:
                    await self.question_queue.initialize()
                
                # Analyze uncertainty
                curiosity_result = await self.curiosity.analyze_response(
                    user_query=message,
                    veda_response=full_response,
                    conversation_id=thread_id,
                    conversation_length=0,  # TODO: track actual length
                    user_id=user_id
                )
                
                if curiosity_result.should_ask and curiosity_result.question:
                    # Inject question naturally at end
                    final_response = f"{full_response}\n\n{curiosity_result.question}"
                    
                    logger.info(
                        "curiosity_question_injected",
                        user_id=user_id,
                        uncertainty=f"{curiosity_result.uncertainty_result.uncertainty_score:.2f}",
                        question_preview=curiosity_result.question[:50]
                    )
            except Exception as e:
                logger.error("curiosity_error", error=str(e), user_id=user_id)
                # Graceful degradation - continue without question
        
        # Yield final response (with question if injected)
        yield final_response

        # 9. BACKGROUND STORAGE (with cognitive metadata)
        # Store only the text part of the message to save DB space
        if len(message) > 20:
            asyncio.create_task(
                self._store_memory_background(
                    message,
                    final_response,
                    task_type,
                    metacognitive_guidance
                )
            )
    
    def _detect_mode(self, message: str) -> str:
        """
        Detect if message is personal or work-related.
        Used for cognitive analysis routing.
        """
        work_keywords = ["sap", "basis", "transaction", "system", "error", "dump", "abap", "hana"]
        personal_keywords = ["feel", "feeling", "happy", "sad", "stressed", "tired", "excited"]
        
        has_work = any(kw in message.lower() for kw in work_keywords)
        has_personal = any(kw in message.lower() for kw in personal_keywords)
        
        if has_work and not has_personal:
            return "work"
        elif has_personal and not has_work:
            return "personal"
        else:
            # Default to personal for ambiguous cases
            return "personal"

    async def _store_memory_background(
        self,
        message: str,
        response: str,
        task_type: str,
        metacognitive_guidance: str = ""
    ):
        """
        Store memory with optional cognitive metadata.
        Now includes Phase 2 metacognitive context.
        """
        has_sap = any(kw in message.lower() for kw in ["sap", "basis"])
        has_personal = any(kw in message.lower() for kw in ["feel", "happy"])
        
        metadata = {
            "task": task_type,
            "cognitive_v3": self.cognitive_enabled,
            "has_metacognition": bool(metacognitive_guidance)
        }

        if has_sap or (not has_personal):
            await self.memory.store(message, response, "work", metadata=metadata)
        if has_personal or (not has_sap):
            await self.memory.store(message, response, "personal", metadata=metadata)

    def _format_context(self, memories: list[dict], context_type: str) -> str:
        if not memories: 
            return ""
        return f"{context_type} Context:\n" + "\n".join([
            f"{i+1}. {m.get('content', '')[:150]}" 
            for i, m in enumerate(memories)
        ])


    def _format_associations(self, associations: list) -> str:
        """Format associations for system prompt (Phase 3)."""
        if not associations:
            return ""
        
        sorted_assocs = sorted(associations, key=lambda a: a.relevance_score, reverse=True)
        top_assocs = sorted_assocs[:2]
        
        lines = ["<related_memories>"]
        lines.append("(Veda naturally recalled these - mention if relevant)")
        
        for i, assoc in enumerate(top_assocs, 1):
            lines.append(f"\n{i}. {assoc.reasoning}")
            lines.append(f"   Content: {assoc.content[:200]}...")
            lines.append(f"   (Relevance: {assoc.relevance_score:.2f})")
        
        lines.append("</related_memories>")
        return "\n".join(lines)
    def _should_trigger_research(self, message: str) -> bool:
        triggers = [r'sap\s*note', r'error\s*code', r'latest', r'version']
        if any(re.search(p, message.lower()) for p in [r'^what\s+is', r'^explain']): 
            return False
        return any(re.search(p, message.lower()) for p in triggers)

    async def process_message(self, message: str, thread_id: str):
        """Legacy non-streaming entry point (maintained for compatibility)."""
        async for chunk in self.process_message_streaming(message, thread_id):
            yield chunk
    
    def enable_cognitive_features(self, enabled: bool = True):
        """
        Toggle Phase 2 metacognitive features on/off.
        Useful for debugging or gradual rollout.
        """
        self.cognitive_enabled = enabled
        logger.info(f"cognitive_features_{'enabled' if enabled else 'disabled'}")
