"""
Test associative memory with real FalkorDB data
"""
import asyncio
from src.brain.memory_manager import MemoryManager
from src.brain.associative_memory import get_associations
import os

async def test():
    # Initialize memory manager
    memory = MemoryManager(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        falkordb_host="localhost",
        falkordb_port=6379,
        falkordb_password=os.getenv("FALKORDB_PASSWORD")
    )
    
    await memory.initialize()
    
    # Test query
    query = "SAP performance issue"
    
    # Get direct memories
    print("1. Getting direct memories...")
    memories = await memory.search(query, memory_type="work", limit=3)
    print(f"   Found {len(memories)} direct memories")
    
    if memories:
        # Get associations
        print("\n2. Finding associations...")
        associations = await get_associations(
            query=query,
            existing_memories=memories,
            graph_driver=memory.work_graphiti.driver,
            memory_type="work",
            max_hops=2,
            min_relevance=0.5
        )
        
        print(f"   Found {len(associations)} associations")
        
        for i, assoc in enumerate(associations, 1):
            print(f"\n   Association {i}:")
            print(f"   - Source: {assoc.source_entity}")
            print(f"   - Target: {assoc.target_entity}")
            print(f"   - Relevance: {assoc.relevance_score:.2f}")
            print(f"   - Reasoning: {assoc.reasoning}")
            print(f"   - Content: {assoc.content[:100]}...")
    else:
        print("   No memories found to associate from")
    
    await memory.close()
    print("\n✓ Test complete!")

if __name__ == "__main__":
    asyncio.run(test())
