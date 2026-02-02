#!/usr/bin/env python3
"""
Dream State - Nightly memory consolidation and learning.

Runs three jobs:
1. Memory consolidation (2 AM)
2. Context cleanup (3 AM)
3. SAP landscape learning (4 AM)
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.core.openrouter_client import OpenRouterClient
from src.brain.memory_manager import MemoryManager
import structlog

logger = structlog.get_logger()


async def consolidate_memories(memory_manager: MemoryManager):
    """Consolidate and strengthen memories."""
    logger.info("dream_state_consolidation_started")
    
    # Consolidate both memory types
    await memory_manager.consolidate_memories("personal")
    await memory_manager.consolidate_memories("work")
    
    logger.info("dream_state_consolidation_complete")


async def cleanup_context(memory_manager: MemoryManager):
    """Remove low-importance or redundant memories."""
    logger.info("dream_state_cleanup_started")
    
    # This would implement logic to:
    # 1. Find memories with importance < 0.3
    # 2. Find duplicate/redundant memories
    # 3. Remove them from graph
    
    logger.info("dream_state_cleanup_complete")


async def learn_sap_issues(client: OpenRouterClient):
    """Research common SAP issues for proactive learning."""
    logger.info("dream_state_learning_started")
    
    # Use Kimi K2.5 (fallback model) to save tokens
    learning_prompt = """Research the 5 most common SAP Basis issues from the past week.
Focus on:
- Kernel patch issues
- Performance problems
- User administration challenges
- Transport errors
- Database connectivity

Summarize in 200 words."""
    
    response = await client.chat(
        messages=[
            {"role": "system", "content": "You are an SAP research assistant."},
            {"role": "user", "content": learning_prompt}
        ],
        task_type="dream_state",
        stream=False,
        temperature=0.3,
    )
    
    logger.info(
        "dream_state_learning_complete",
        learned=response["choices"][0]["message"]["content"][:100]
    )


async def run_dream_cycle():
    """Execute full dream state cycle."""
    logger.info("dream_cycle_started", time=datetime.now().isoformat())
    
    # Initialize clients
    client = OpenRouterClient(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        daily_budget=0.17,  # Dream state budget
    )
    
    memory = MemoryManager(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        falkordb_password=os.getenv("FALKORDB_PASSWORD"),
    )
    
    await memory.initialize()
    
    try:
        # Run all dream state jobs
        await consolidate_memories(memory)
        await cleanup_context(memory)
        await learn_sap_issues(client)
        
    except Exception as e:
        logger.error("dream_cycle_error", error=str(e))
    finally:
        await memory.close()
        await client.close()
    
    logger.info("dream_cycle_complete")


if __name__ == "__main__":
    asyncio.run(run_dream_cycle())
