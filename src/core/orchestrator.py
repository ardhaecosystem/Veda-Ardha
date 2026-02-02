"""
IMPROVED VERSION: Enhanced mode classification with:
1. Expanded SAP keyword detection
2. Conversation context awareness
3. "Sticky" work mode (stays in work mode for multi-turn technical conversations)
4. Better pattern matching
"""

import asyncio
from typing import TypedDict, Literal, Annotated, Optional, AsyncGenerator
from datetime import datetime
import operator
import re

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field
import structlog

from .openrouter_client import OpenRouterClient
from ..persona.veda_persona import VedaPersona, is_technical_query
from ..brain.memory_manager import MemoryManager
from ..eyes.search_tool import SearchTool

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


class ModeClassification(BaseModel):
    """Classification of conversation mode."""
    mode: Literal["personal", "work"] = Field(
        description="Whether this is personal conversation or SAP work-related"
    )
    task_type: Literal["planning", "coding", "chat", "research"] = Field(
        description="Type of task being requested"
    )
    is_technical: bool = Field(
        description="Whether this requires technical/coding response"
    )
    detected_emotion: Optional[str] = Field(
        default=None,
        description="User's emotional state if detectable"
    )


class VedaOrchestrator:
    """
    Main orchestrator for Veda AI system.

    Handles:
    - Mode detection (personal vs work)
    - Model routing based on task type
    - Persona activation/deactivation
    - Memory context retrieval
    - Web search for research tasks
    - Response generation with streaming
    """

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        memory_manager: MemoryManager,
    ):
        self.client = openrouter_client
        self.memory = memory_manager
        self.persona = VedaPersona()
        self.search_tool = SearchTool()
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
        
        # NEW: Track conversation context per thread
        self.thread_contexts = {}  # {thread_id: {"mode": "work", "last_technical": timestamp}}

    def _build_graph(self) -> StateGraph:
        """Build LangGraph workflow."""

        workflow = StateGraph(ConversationState)

        # Add nodes
        workflow.add_node("classify_mode", self._classify_mode)
        workflow.add_node("retrieve_memory", self._retrieve_memory)
        workflow.add_node("perform_research", self._perform_research)
        workflow.add_node("personal_response", self._personal_response)
        workflow.add_node("work_response", self._work_response)
        workflow.add_node("store_memory", self._store_memory)

        # Define edges
        workflow.add_edge(START, "classify_mode")
        workflow.add_edge("classify_mode", "retrieve_memory")

        workflow.add_conditional_edges(
            "retrieve_memory",
            self._route_after_memory,
            {
                "research": "perform_research",
                "personal": "personal_response",
                "work": "work_response",
            }
        )

        workflow.add_edge("perform_research", "work_response")

        workflow.add_edge("personal_response", "store_memory")
        workflow.add_edge("work_response", "store_memory")
        workflow.add_edge("store_memory", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _is_work_mode(self, message: str, memories: list = None, thread_id: str = None) -> bool:
        """
        IMPROVED: Enhanced work mode detection with multiple signals.
        
        Returns True if this is work/technical conversation.
        """
        
        message_lower = message.lower()
        
        # SIGNAL 1: Comprehensive SAP keyword list
        sap_keywords = [
            # Core SAP
            "sap", "basis", "abap", "hana", "netweaver", "s/4hana", "btp",
            
            # Transaction codes (common patterns)
            "tcode", "t-code", "transaction", "su01", "su10", "sm21", "st22", 
            "db02", "sm50", "sm51", "sm12", "sm13", "stms", "se38", "se80",
            "sm37", "sm36", "rz10", "rz20", "al08", "pfcg", "suim",
            
            # SAP Operations
            "user", "role", "authorization", "profile", "transport", "kernel",
            "instance", "system", "client", "mandant", "lock", "unlock",
            "assign", "create user", "delete user", "password reset",
            
            # Technical terms
            "error", "dump", "short dump", "system log", "syslog",
            "database", "tablespace", "backup", "restore", "performance",
            "tuning", "monitor", "troubleshoot", "debug",
            
            # Automation/Scripting
            "script", "automate", "batch", "job", "schedule",
            "python", "shell", "bash", "ansible", "terraform",
            
            # SAP Components
            "ecc", "ecc6", "erp", "scm", "srm", "crm", "bw", "bi",
            "fiori", "gateway", "web dispatcher", "solution manager",
            
            # Infrastructure
            "server", "linux", "windows", "oracle", "db2", "sybase",
            "maxdb", "ssl", "certificate", "port", "firewall"
        ]
        
        # Check for SAP keywords
        if any(kw in message_lower for kw in sap_keywords):
            logger.info("work_mode_detected", reason="sap_keyword", message=message[:50])
            return True
        
        # SIGNAL 2: SAP transaction code pattern (4-5 chars, alphanumeric)
        # Matches: SU01, SM21, ST22, etc.
        tcode_pattern = r'\b[A-Z]{2}\d{2,3}\b|\b[A-Z]{4}\b'
        if re.search(tcode_pattern, message):
            logger.info("work_mode_detected", reason="tcode_pattern", message=message[:50])
            return True
        
        # SIGNAL 3: Technical question patterns
        technical_patterns = [
            r'how (?:do i|to|can i).*(configure|install|setup|fix|troubleshoot)',
            r'what is.*(command|syntax|parameter|setting)',
            r'how to.*(create|delete|modify|change|update|lock|unlock)',
            r'step(?:-|\s)?by(?:-|\s)?step',
            r'can you (?:help|show|explain).*(code|script|command)',
        ]
        
        for pattern in technical_patterns:
            if re.search(pattern, message_lower):
                logger.info("work_mode_detected", reason="technical_pattern", message=message[:50])
                return True
        
        # SIGNAL 4: Memory context from previous conversation
        if memories:
            # Check if recent memories were work-related
            work_memory_indicators = ["sap", "transaction", "system", "basis", "error", "user"]
            for mem in memories[:3]:  # Check top 3 memories
                mem_content = mem.get("content", "").lower()
                if any(ind in mem_content for ind in work_memory_indicators):
                    logger.info("work_mode_detected", reason="memory_context", 
                              memory_snippet=mem_content[:50])
                    return True
        
        # SIGNAL 5: Thread context (sticky mode)
        # If we were recently in work mode, stay in work mode for related questions
        if thread_id and thread_id in self.thread_contexts:
            context = self.thread_contexts[thread_id]
            if context.get("mode") == "work":
                # Stay in work mode for follow-up questions
                followup_patterns = [
                    r'^(?:how|what|can|could|would|should|please|ok|okay|and)',
                    r'(?:step|next|then|after|also|additionally)',
                    r'(?:same|this|that|it|these)'
                ]
                for pattern in followup_patterns:
                    if re.search(pattern, message_lower):
                        logger.info("work_mode_detected", reason="sticky_followup", 
                                  message=message[:50])
                        return True
        
        # Default: personal mode
        return False
    
    def _update_thread_context(self, thread_id: str, mode: str):
        """Update thread context to track conversation mode."""
        if thread_id:
            self.thread_contexts[thread_id] = {
                "mode": mode,
                "last_update": datetime.now()
            }
            
            # Cleanup old thread contexts (older than 1 hour)
            cutoff = datetime.now().timestamp() - 3600
            self.thread_contexts = {
                tid: ctx for tid, ctx in self.thread_contexts.items()
                if ctx["last_update"].timestamp() > cutoff
            }

    async def _classify_mode(self, state: ConversationState) -> dict:
        """Classify conversation mode and task type."""

        last_message = state["messages"][-1]["content"]

        # Use lightweight classification
        classification_prompt = f"""Classify this message:
"{last_message}"

Respond with JSON:
- mode: "personal" (life, feelings, casual chat) or "work" (SAP, technical, automation)
- task_type: "planning" (complex reasoning), "coding" (generate code), "chat" (conversation), "research" (need to search)
- is_technical: true/false
- detected_emotion: user's emotion if detectable, null otherwise"""

        response = await self.client.chat(
            messages=[
                {"role": "system", "content": "You are a classifier. Respond only with valid JSON."},
                {"role": "user", "content": classification_prompt}
            ],
            task_type="chat",
            stream=False,
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        try:
            import json
            classification = json.loads(response["choices"][0]["message"]["content"])

            return {
                "mode": classification.get("mode", "personal"),
                "task_type": classification.get("task_type", "chat"),
                "persona_active": not classification.get("is_technical", False),
                "user_emotion": classification.get("detected_emotion"),
            }
        except:
            # Default to personal mode with chat
            return {
                "mode": "personal",
                "task_type": "chat",
                "persona_active": True,
                "user_emotion": None,
            }

    async def _retrieve_memory(self, state: ConversationState) -> dict:
        """Retrieve relevant memories based on mode."""

        last_message = state["messages"][-1]["content"]
        mode = state["mode"]

        # Search in mode-specific memory
        memories = await self.memory.search(
            query=last_message,
            memory_type=mode,
            limit=5
        )

        return {"memory_context": memories}

    def _route_after_memory(self, state: ConversationState) -> str:
        """Route based on task type and mode."""
        if state["task_type"] == "research":
            return "research"
        return state["mode"]

    async def _perform_research(self, state: ConversationState) -> dict:
        """Perform web search for unknown SAP issues."""

        last_message = state["messages"][-1]["content"]

        logger.info("performing_research", query=last_message[:50])

        category = "sap" if any(kw in last_message.lower()
                               for kw in ["sap", "basis", "abap", "hana"]) else "it"

        search_results = await self.search_tool.search(
            query=last_message,
            category=category,
            max_results=5
        )

        logger.info("research_completed", results_length=len(search_results))

        return {"search_results": search_results}

    async def _personal_response(self, state: ConversationState) -> dict:
        """Generate personal mode response with Veda persona."""

        system_prompt = self.persona.get_system_prompt(
            user_emotion=state.get("user_emotion"),
            memory_context=state.get("memory_context", [])
        )

        messages = [
            {"role": "system", "content": system_prompt},
            *state["messages"]
        ]

        messages = self.memory.compress_context(messages, threshold=10)

        response_chunks = []
        async for chunk in self.client.chat(
            messages=messages,
            task_type="chat",
            stream=True,
            temperature=0.8,
        ):
            response_chunks.append(chunk)

        return {"response": "".join(response_chunks)}

    async def _work_response(self, state: ConversationState) -> dict:
        """Generate work mode response - SAP Basis Expert."""

        task_type = state["task_type"]
        memory_context = state.get("memory_context", [])
        search_results = state.get("search_results")

        system_prompt = self._build_sap_expert_prompt(memory_context, search_results)

        messages = [
            {"role": "system", "content": system_prompt},
            *state["messages"]
        ]

        messages = self.memory.compress_context(messages, threshold=10)

        response_chunks = []
        async for chunk in self.client.chat(
            messages=messages,
            task_type=task_type,
            stream=True,
            temperature=0.3 if task_type == "coding" else 0.5,
        ):
            response_chunks.append(chunk)

        return {"response": "".join(response_chunks)}

    def _build_sap_expert_prompt(self, memory_context: list, search_results: Optional[str] = None) -> str:
        """Build SAP Basis expert system prompt."""

        context_str = ""
        if memory_context:
            context_str = "\n\nRelevant context from previous interactions:\n"
            for mem in memory_context:
                context_str += f"- {mem.get('content', '')}\n"

        search_str = ""
        if search_results:
            search_str = f"\n\nExternal research findings:\n{search_results}\n"

        return f"""You are an expert SAP Basis Consultant with 15+ years of experience.

Your expertise includes:
- SAP Basis administration across all versions (NetWeaver, S/4HANA, BTP)
- System installations, upgrades, and migrations
- Performance tuning and optimization
- Security hardening and user administration
- Transport management and landscape configuration
- Integration with databases (HANA, Oracle, MSSQL, DB2)
- Automation scripting (bash, Python, ABAP)
- High availability and disaster recovery
- Cloud deployments (AWS, Azure, GCP)

Guidelines:
1. Provide exact, step-by-step solutions
2. Include transaction codes (e.g., SM21, ST22, DB02)
3. Specify which SID/instance commands apply to
4. Always cross-verify critical operations
5. Identify if an issue belongs to Basis team or another team
6. Suggest automation opportunities where applicable
7. Consider the user manages 60 SAP systems
8. If external research is provided, integrate those findings into your answer

DO NOT include any persona, casual language, or emotional responses.
Be direct, technical, and precise.
{context_str}{search_str}"""

    async def _store_memory(self, state: ConversationState) -> dict:
        """Store conversation in appropriate memory space."""

        last_user_msg = state["messages"][-1]["content"]
        response = state["response"]

        if len(last_user_msg) > 20:
            await self.memory.store(
                user_message=last_user_msg,
                assistant_response=response,
                memory_type=state["mode"],
                metadata={
                    "task_type": state["task_type"],
                    "timestamp": datetime.now().isoformat(),
                    "persona_active": state["persona_active"],
                }
            )

        return {}

    async def process_message(
        self,
        message: str,
        thread_id: str,
    ) -> AsyncGenerator[str, None]:
        """Process incoming message and stream response."""

        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "messages": [{"role": "user", "content": message}],
            "mode": "personal",
            "task_type": "chat",
            "persona_active": True,
            "user_emotion": None,
            "response": "",
            "memory_context": [],
            "search_results": None,
        }

        result = await self.graph.ainvoke(initial_state, config)
        yield result["response"]

    async def process_message_streaming(
        self,
        message: str,
        thread_id: str,
    ):
        """
        Process message with TRUE streaming (bypasses LangGraph for speed).
        IMPROVED: Better mode classification with context awareness.
        """

        # Retrieve memories first (needed for classification)
        # Try both personal and work memory to get context
        personal_memories = await self.memory.search(
            query=message,
            memory_type="personal",
            limit=3
        )
        work_memories = await self.memory.search(
            query=message,
            memory_type="work",
            limit=3
        )

        # IMPROVED: Use enhanced classification
        is_work = self._is_work_mode(
            message, 
            memories=work_memories,  # Pass work memories for context
            thread_id=thread_id
        )

        mode = "work" if is_work else "personal"
        persona_active = not is_work
        
        # Update thread context for sticky mode
        self._update_thread_context(thread_id, mode)
        
        # Use appropriate memories based on detected mode
        memories = work_memories if is_work else personal_memories

        logger.info(
            "mode_classified",
            mode=mode,
            persona_active=persona_active,
            message_preview=message[:50],
            thread_id=thread_id
        )

        # Build prompt based on mode
        if persona_active:
            system_prompt = self.persona.get_system_prompt(
                user_emotion=None,
                memory_context=memories
            )
            task_type = "chat"
        else:
            system_prompt = self._build_sap_expert_prompt(memories, None)
            task_type = "coding" if "code" in message.lower() else "chat"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]

        # Stream response from OpenRouter
        full_response = ""
        response_generator = await self.client.chat(
            messages=messages,
            task_type=task_type,
            stream=True,
            temperature=0.8 if persona_active else 0.3,
        )

        async for chunk in response_generator:
            full_response += chunk
            yield chunk

        # Store memory in background
        if len(message) > 20:
            asyncio.create_task(
                self.memory.store(
                    user_message=message,
                    assistant_response=full_response,
                    memory_type=mode,
                    metadata={
                        "task_type": task_type,
                        "timestamp": datetime.now().isoformat(),
                        "persona_active": persona_active,
                    }
                )
            )
