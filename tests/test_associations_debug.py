"""
Debug test - shows associations even if below threshold
"""
import asyncio
from src.brain.memory_manager import MemoryManager
from src.brain.associative_memory import get_associations
import os

async def test():
    memory = MemoryManager(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        falkordb_host="localhost",
        falkordb_port=6379,
        falkordb_password=os.getenv("FALKORDB_PASSWORD")
    )
    
    await memory.initialize()
    
    query = "SAP performance issue"
    
    print("1. Getting direct memories...")
    memories = await memory.search(query, memory_type="work", limit=3)
    print(f"   Found {len(memories)} direct memories")
    
    if memories:
        print("\n2. Finding associations (DEBUG - threshold=0.3)...")
        associations = await get_associations(
            query=query,
            existing_memories=memories,
            graph_driver=memory.work_graphiti.driver,
            memory_type="work",
            max_hops=2,
            min_relevance=0.3  # LOWER threshold to see what was filtered
        )
        
        print(f"   Found {len(associations)} associations\n")
        
        for i, assoc in enumerate(associations, 1):
            print(f"   Association {i}:")
            print(f"   - Relevance: {assoc.relevance_score:.2f}")
            print(f"   - Source Entity: {assoc.source_entity}")
            print(f"   - Target Entity: {assoc.target_entity}")
            print(f"   - Path: {' → '.join(assoc.relationship_path)}")
            print(f"   - Reasoning: {assoc.reasoning}")
            print(f"   - Content: {assoc.content[:150]}...")
            print()
    
    await memory.close()
    print("✓ Debug test complete!")

if __name__ == "__main__":
    asyncio.run(test())
