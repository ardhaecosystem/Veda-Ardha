"""
Test uncertainty scoring with various query types
"""
from src.cognition.uncertainty_scorer import check_uncertainty

# Test cases
test_cases = [
    {
        "name": "Clear specific query",
        "query": "How do I check CPU usage on PROD SAP system using ST06?",
        "response": "To check CPU usage on PROD, use transaction ST06.",
        "expected_uncertain": False
    },
    {
        "name": "Ambiguous query - vague object",
        "query": "Check the system",
        "response": "I'll check ST06 for CPU and memory usage.",
        "expected_uncertain": True
    },
    {
        "name": "Hedging response",
        "query": "What's the best way to optimize performance?",
        "response": "It depends on the issue. Maybe check ST06, or possibly ST04 if it's database-related.",
        "expected_uncertain": True
    },
    {
        "name": "Pronoun without context",
        "query": "Restart it",
        "response": "I'll restart the system now.",
        "expected_uncertain": True
    },
    {
        "name": "Which question without specifics",
        "query": "Which instance should I use?",
        "response": "You can use either DEV or QA for testing.",
        "expected_uncertain": True
    }
]

print("Testing Uncertainty Scorer")
print("=" * 60)

for i, test in enumerate(test_cases, 1):
    result = check_uncertainty(
        query=test["query"],
        response=test["response"],
        conversation_length=0,
        threshold=0.45
    )
    
    passed = result.should_ask_clarification == test["expected_uncertain"]
    status = "✓ PASS" if passed else "✗ FAIL"
    
    print(f"\nTest {i}: {status}")
    print(f"Name: {test['name']}")
    print(f"Query: '{test['query']}'")
    print(f"Uncertainty: {result.uncertainty_score:.2f}")
    print(f"  - Query ambiguity: {result.query_ambiguity:.2f}")
    print(f"  - Response hedging: {result.response_hedging:.2f}")
    print(f"  - Context missing: {result.context_missing:.2f}")
    print(f"Should ask: {result.should_ask_clarification}")
    print(f"Expected: {test['expected_uncertain']}")
    if result.suggested_question:
        print(f"Suggested: {result.suggested_question}")

print("\n" + "=" * 60)
print("Test suite complete!")
