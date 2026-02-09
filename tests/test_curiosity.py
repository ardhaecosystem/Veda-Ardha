"""
Test curiosity system with various scenarios
"""
import asyncio
from src.cognition.curiosity_system import CuriositySystem

async def test():
    curiosity = CuriositySystem(
        uncertainty_threshold=0.45,
        max_questions_per_conversation=2
    )
    
    test_cases = [
        {
            "name": "Ambiguous query - should ask",
            "query": "Check the system",
            "response": "I'll check ST06 for CPU and memory usage.",
            "conv_id": "test1",
            "conv_len": 1,
            "expected_ask": True
        },
        {
            "name": "Clear query - should not ask",
            "query": "How do I check CPU on PROD using ST06?",
            "response": "To check CPU on PROD, use transaction ST06.",
            "conv_id": "test2",
            "conv_len": 1,
            "expected_ask": False
        },
        {
            "name": "Pronoun without context - should ask",
            "query": "Restart it",
            "response": "I'll restart the system.",
            "conv_id": "test3",
            "conv_len": 0,
            "expected_ask": True
        },
        {
            "name": "Rate limit test - 1st question",
            "query": "Fix that",
            "response": "I'll fix the issue.",
            "conv_id": "rate_limit",
            "conv_len": 1,
            "expected_ask": True
        },
        {
            "name": "Rate limit test - 2nd question",
            "query": "Check this",
            "response": "I'll check it.",
            "conv_id": "rate_limit",  # Same conversation
            "conv_len": 2,
            "expected_ask": True
        },
        {
            "name": "Rate limit test - 3rd question (BLOCKED)",
            "query": "Show me that",
            "response": "I'll show you.",
            "conv_id": "rate_limit",  # Same conversation
            "conv_len": 3,
            "expected_ask": False  # Max 2 questions reached
        }
    ]
    
    print("Testing Curiosity System")
    print("=" * 70)
    
    for i, test in enumerate(test_cases, 1):
        result = await curiosity.analyze_response(
            user_query=test["query"],
            veda_response=test["response"],
            conversation_id=test["conv_id"],
            conversation_length=test["conv_len"]
        )
        
        passed = result.should_ask == test["expected_ask"]
        status = "✓ PASS" if passed else "✗ FAIL"
        
        print(f"\nTest {i}: {status}")
        print(f"Name: {test['name']}")
        print(f"Query: '{test['query']}'")
        print(f"Uncertainty: {result.uncertainty_result.uncertainty_score:.2f}")
        print(f"Should ask: {result.should_ask}")
        print(f"Expected: {test['expected_ask']}")
        print(f"Reasoning: {result.reasoning}")
        
        if result.should_ask and result.question:
            print(f"Question: {result.question}")
    
    print("\n" + "=" * 70)
    print("Test suite complete!")

if __name__ == "__main__":
    asyncio.run(test())
