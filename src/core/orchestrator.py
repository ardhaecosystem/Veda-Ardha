"""
Veda 2.0 Orchestrator: Unified Persona, Token Optimization, SAP Agent, Vision, and Streaming.
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
        full_message_payload: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Processes message with Vision Support.
        'message' is text-only (for logic).
        'full_message_payload' is the raw list (for the Vision Model).
        """
        
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

        # 3. INTELLIGENCE LAYER
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

        # 4. BUILD UNIFIED PROMPT
        current_hour = datetime.now().hour
        system_prompt = self.persona.get_unified_system_prompt(
            personal_context=personal_context,
            work_context=work_context,
            user_emotion=None,
            current_hour=current_hour,
        )
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
            if "code" in message.lower() or "script" in message.lower(): task_type = "coding"
            elif any(p in message.lower() for p in ["analyze", "plan"]): task_type = "planning"

        logger.info("processing_request", task_type=task_type, has_image=bool(full_message_payload))

        # 7. STREAM RESPONSE
        full_response = ""
        async for chunk in await self.client.chat(messages=messages, task_type=task_type, stream=True, temperature=0.7):
            full_response += chunk
            yield chunk

        # 8. POST-PROCESS
        cleaned_response = clean_code_blocks(full_response)

        # 9. BACKGROUND STORAGE
        # Store only the text part of the message to save DB space
        if len(message) > 20:
            asyncio.create_task(self._store_memory_background(message, cleaned_response, task_type))

    async def _store_memory_background(self, message: str, response: str, task_type: str):
        has_sap = any(kw in message.lower() for kw in ["sap", "basis"])
        has_personal = any(kw in message.lower() for kw in ["feel", "happy"])

        if has_sap or (not has_personal):
            await self.memory.store(message, response, "work", metadata={"task": task_type})
        if has_personal or (not has_sap):
            await self.memory.store(message, response, "personal", metadata={"task": task_type})

    def _format_context(self, memories: list[dict], context_type: str) -> str:
        if not memories: return ""
        return f"{context_type} Context:\n" + "\n".join([f"{i+1}. {m.get('content', '')[:150]}" for i, m in enumerate(memories)])

    def _should_trigger_research(self, message: str) -> bool:
        triggers = [r'sap\s*note', r'error\s*code', r'latest', r'version']
        if any(re.search(p, message.lower()) for p in [r'^what\s+is', r'^explain']): return False
        return any(re.search(p, message.lower()) for p in triggers)

    async def process_message(self, message: str, thread_id: str):
        async for chunk in self.process_message_streaming(message, thread_id):
            yield chunk
