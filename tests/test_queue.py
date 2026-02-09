"""
Test question queue with Redis integration
"""
import asyncio
from src.cognition.question_queue import QuestionQueue

async def test():
    # Initialize queue (uses Phase 1 Redis on port 6380)
    queue = QuestionQueue(
        redis_url="redis://localhost:6380",
        cooldown_seconds=5,  # Short for testing
        max_attempts=2
    )
    
    print("Testing Question Queue")
    print("=" * 70)
    
    try:
        # Test 1: Initialize connection
        print("\nTest 1: Connecting to Redis...")
        await queue.initialize()
        print("✓ Connected to Redis on port 6380")
        
        # Clean up any old test data
        await queue.clear_conversation_queue("test_conv")
        
        # Test 2: Add questions with different priorities
        print("\nTest 2: Adding questions with priorities...")
        q1 = await queue.add_question(
            question_text="Low priority question",
            conversation_id="test_conv",
            priority=0.3,
            context={"type": "low"}
        )
        print(f"✓ Added question 1 (priority 0.3): {q1}")
        
        q2 = await queue.add_question(
            question_text="High priority question",
            conversation_id="test_conv",
            priority=0.9,
            context={"type": "high"}
        )
        print(f"✓ Added question 2 (priority 0.9): {q2}")
        
        q3 = await queue.add_question(
            question_text="Medium priority question",
            conversation_id="test_conv",
            priority=0.6,
            context={"type": "medium"}
        )
        print(f"✓ Added question 3 (priority 0.6): {q3}")
        
        # Test 3: Check queue stats
        print("\nTest 3: Queue statistics...")
        stats = await queue.get_queue_stats("test_conv")
        print(f"✓ Queue stats: {stats}")
        expected_count = 3
        if stats["count"] == expected_count:
            print(f"✓ Correct count: {expected_count}")
        else:
            print(f"✗ Wrong count: expected {expected_count}, got {stats['count']}")
        
        # Test 4: Retrieve highest priority first
        print("\nTest 4: Retrieving highest priority question...")
        next_q = await queue.get_next_question("test_conv")
        if next_q:
            print(f"✓ Retrieved: '{next_q.question_text}' (priority {next_q.priority})")
            if next_q.priority == 0.9:
                print("✓ Correct priority order (0.9 is highest)")
            else:
                print(f"✗ Wrong priority: expected 0.9, got {next_q.priority}")
        else:
            print("✗ No question retrieved")
        
        # Test 5: Cooldown enforcement
        print("\nTest 5: Cooldown enforcement...")
        next_q2 = await queue.get_next_question("test_conv")
        if next_q2:
            print(f"✗ Cooldown failed - retrieved: '{next_q2.question_text}'")
        else:
            print("✓ Cooldown working - no question retrieved immediately")
        
        # Wait for cooldown
        print("  Waiting 6 seconds for cooldown...")
        await asyncio.sleep(6)
        
        next_q3 = await queue.get_next_question("test_conv")
        if next_q3:
            print(f"✓ After cooldown - retrieved: '{next_q3.question_text}' (priority {next_q3.priority})")
        else:
            print("✗ No question after cooldown")
        
        # Test 6: Duplicate detection
        print("\nTest 6: Duplicate detection...")
        duplicate_id = await queue.add_question(
            question_text="Low priority question",  # Same as q1
            conversation_id="test_conv",
            priority=0.5
        )
        if duplicate_id == q1:
            print(f"✓ Duplicate detected - returned existing ID: {duplicate_id}")
        else:
            print(f"✗ Duplicate not detected - got new ID: {duplicate_id}")
        
        # Test 7: Mark question as asked
        print("\nTest 7: Marking question as asked...")
        if next_q:
            await queue.mark_question_asked(next_q.question_id, "test_conv")
            print(f"✓ Marked question {next_q.question_id} as asked")
        
        # Test 8: Final queue stats
        print("\nTest 8: Final queue stats...")
        final_stats = await queue.get_queue_stats("test_conv")
        print(f"✓ Final stats: {final_stats}")
        print(f"  Remaining questions: {final_stats['count']}")
        
        # Cleanup
        print("\nCleaning up...")
        await queue.clear_conversation_queue("test_conv")
        print("✓ Test conversation cleared")
        
    finally:
        await queue.close()
        print("\n✓ Redis connection closed")
    
    print("\n" + "=" * 70)
    print("Test suite complete!")

if __name__ == "__main__":
    asyncio.run(test())
