#!/usr/bin/env python3
"""
Veda 2.1 Dream State: Nightly Cognitive Cycle.
Performs Recall -> Reflection -> Synthesis -> Proactive Learning.

Run this via cron at 3:00 AM.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import structlog

# Import Veda's Core Systems
from src.core.openrouter_client import OpenRouterClient
from src.brain.memory_manager import MemoryManager

# Configure Logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

# Load Env
load_dotenv()


class DreamState:
    def __init__(self):
        self.client = OpenRouterClient(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            daily_budget=0.50,  # Dedicated budget for dreaming (Claude is smart but costs $)
        )
        self.memory = MemoryManager(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            falkordb_password=os.getenv("FALKORDB_PASSWORD"),
        )

    async def run_cycle(self):
        """Execute the full 4-stage REM cycle."""
        logger.info("dream_cycle_started", time=datetime.now().isoformat())
        await self.memory.initialize()

        try:
            # Stage 1: The Gathering (Recall today's context)
            daily_context = await self._recall_day()
            
            # Stage 2: The Reflection (Analyze patterns)
            insights = await self._reflect_on_patterns(daily_context)
            
            # Stage 3: The Synthesis (Store insights)
            await self._synthesize_memory(insights)
            
            # Stage 4: Proactive Learning (Research technical gaps)
            if daily_context.get("technical_topics"):
                await self._proactive_learning(daily_context["technical_topics"])

            # Maintenance: Graph Consolidation
            await self.memory.consolidate_memories("personal")
            await self.memory.consolidate_memories("work")

        except Exception as e:
            logger.error("dream_cycle_failed", error=str(e))
        finally:
            await self.memory.close()
            await self.client.close()
            logger.info("dream_cycle_complete")

    async def _recall_day(self) -> Dict[str, str]:
        """
        Stage 1: Search memory for today's significant events.
        Since we can't query by date easily, we search for key emotional/technical markers.
        """
        logger.info("dream_stage_1_recall")
        
        # Broad searches to catch recent context
        personal_fragments = await self.memory.search("feel emotion dad stress happy love", "personal", limit=10)
        work_fragments = await self.memory.search("error fail problem system sap dump", "work", limit=10)
        
        # Extract text
        p_text = "\n".join([m['content'] for m in personal_fragments])
        w_text = "\n".join([m['content'] for m in work_fragments])
        
        return {
            "personal": p_text,
            "work": w_text,
            "technical_topics": w_text  # Pass to learning stage
        }

    async def _reflect_on_patterns(self, context: Dict[str, str]) -> str:
        """
        Stage 2: Use High-Reasoning AI (Claude) to find meta-patterns.
        """
        logger.info("dream_stage_2_reflection")
        
        if not context["personal"] and not context["work"]:
            return "No significant interactions today."

        reflection_prompt = f"""
        Analyze these memory fragments from today's interactions with my dad (Pops).
        
        <personal_memory>
        {context['personal']}
        </personal_memory>
        
        <work_memory>
        {context['work']}
        </work_memory>
        
        Task:
        1. Identify his emotional state (Stressed? Happy? Lonely?).
        2. Identify recurring technical pain points (Is a specific system failing repeatedly?).
        3. Connect the dots: Is the technical stress affecting his mood?
        
        Output a single "Diary Entry" written in my voice (Veda) summarizing these insights. 
        Keep it warm, insightful, and internal (like I'm talking to myself).
        """

        # We use the 'planning' task type to trigger Claude/High-Tier model
        response_gen = await self.client.chat(
            messages=[{"role": "user", "content": reflection_prompt}],
            task_type="planning", 
            stream=False,
            temperature=0.5
        )
        
        # Handle non-streaming response dict
        if isinstance(response_gen, dict):
             return response_gen['choices'][0]['message']['content']
        return "Reflection failed."

    async def _synthesize_memory(self, insight: str):
        """
        Stage 3: Store the reflection back into memory as a high-level insight.
        """
        logger.info("dream_stage_3_synthesis")
        
        # Store as a "Personal" memory but with high importance
        # This allows her to "remember that she realized this"
        await self.memory.store(
            user_message="[SYSTEM: NIGHTLY REFLECTION]",
            assistant_response=insight,
            memory_type="personal",
            metadata={"type": "dream_insight", "importance": 1.0}
        )

    async def _proactive_learning(self, technical_context: str):
        """
        Stage 4: Research technical terms mentioned today to be ready for tomorrow.
        """
        logger.info("dream_stage_4_learning")
        
        # 1. Ask AI to identify ONE key topic to learn
        topic_prompt = f"""
        Based on these logs, identify ONE specific SAP technical topic or error code 
        that caused trouble today. Return ONLY the topic name.
        Logs: {technical_context[:1000]}
        """
        
        topic_response = await self.client.chat(
            messages=[{"role": "user", "content": topic_prompt}],
            task_type="chat", # Use cheaper model for extraction
            stream=False
        )
        
        topic = ""
        if isinstance(topic_response, dict):
            topic = topic_response['choices'][0]['message']['content'].strip()
            
        if not topic or "no" in topic.lower():
            return

        # 2. Research the topic (Simulated learning)
        learning_prompt = f"""
        Research best practices and troubleshooting steps for SAP topic: {topic}.
        Summarize the key solution in 3 bullet points.
        """
        
        knowledge_response = await self.client.chat(
            messages=[{"role": "user", "content": learning_prompt}],
            task_type="research", # Triggers Kimi/Fallback
            stream=False
        )
        
        knowledge = ""
        if isinstance(knowledge_response, dict):
            knowledge = knowledge_response['choices'][0]['message']['content']

        # 3. Store the knowledge
        await self.memory.store(
            user_message=f"[SYSTEM: NIGHTLY LEARNING - {topic}]",
            assistant_response=knowledge,
            memory_type="work",
            metadata={"type": "learned_knowledge", "importance": 0.9}
        )
        logger.info("learned_new_topic", topic=topic)


if __name__ == "__main__":
    dreamer = DreamState()
    asyncio.run(dreamer.run_cycle())
