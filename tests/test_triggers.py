"""
Test trigger detection with various message types
"""
from src.brain.memory_triggers import should_run_associations

# Test cases
test_cases = [
    {
        "message": "Hey!",
        "expected": False,
        "reason": "Simple greeting"
    },
    {
        "message": "What did we discuss about SAP performance earlier?",
        "expected": True,
        "reason": "Explicit context reference"
    },
    {
        "message": "ok",
        "expected": False,
        "reason": "One-word reply"
    },
    {
        "message": "Can you compare the two approaches we discussed?",
        "expected": True,
        "reason": "Comparison request"
    },
    {
        "message": "I'm having an SAP system performance issue with database queries running slow",
        "expected": True,
        "reason": "Complex technical question"
    },
    {
        "message": "Thanks!",
        "expected": False,
        "reason": "Simple affirmation"
    },
    {
        "message": "What about that other solution you mentioned?",
        "expected": True,
        "reason": "Follow-up question"
    }
]

print("Testing Trigger Detection Logic\n" + "="*50)

for i, test in enumerate(test_cases, 1):
    result = should_run_associations(
        message=test["message"],
        conversation_history=[],
        has_direct_memories=True  # Assume memories exist
    )
    
    passed = result.should_trigger == test["expected"]
    status = "✓ PASS" if passed else "✗ FAIL"
    
    print(f"\nTest {i}: {status}")
    print(f"Message: '{test['message']}'")
    print(f"Expected: {test['expected']} ({test['reason']})")
    print(f"Got: {result.should_trigger} ({result.reason})")
    print(f"Confidence: {result.confidence:.2f}")

print("\n" + "="*50)
print("Test suite complete!")
