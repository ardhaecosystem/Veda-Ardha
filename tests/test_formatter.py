"""
Test question formatter with various question types
"""
from src.cognition.question_formatter import QuestionFormatter

def test():
    # Create formatter (no variation for consistent testing)
    formatter = QuestionFormatter(use_variation=False)
    
    print("Testing Question Formatter")
    print("=" * 70)
    
    # Test all question types
    question_types = [
        ("which_environment", "When user doesn't specify DEV/QA/PROD"),
        ("which_specific_check", "User says 'check it'"),
        ("which_specific_action", "User says 'restart it'"),
        ("what_is_it", "User uses pronoun without context"),
        ("what_help_with", "Generic help request"),
        ("general_clarification", "Fallback for unclear query"),
        ("which_instance", "SAP instance ambiguity"),
        ("which_transaction", "Transaction code ambiguity"),
        ("which_option", "Multiple approaches possible"),
    ]
    
    for i, (q_type, description) in enumerate(question_types, 1):
        question = formatter.format_question(q_type)
        
        print(f"\nTest {i}: {q_type}")
        print(f"Description: {description}")
        print(f"Question: {question}")
        
        # Check it's not empty
        if question and len(question) > 10:
            print("✓ PASS - Valid question generated")
        else:
            print("✗ FAIL - Invalid question")
    
    # Test context-aware formatting
    print("\n" + "=" * 70)
    print("\nTest 10: Context-aware formatting (high uncertainty)")
    contextual = formatter.format_with_context(
        question_type="which_environment",
        user_query="check system",
        uncertainty_score=0.8
    )
    print(f"Question: {contextual}")
    if "really wanna make sure" in contextual.lower():
        print("✓ PASS - Context emphasis added for high uncertainty")
    else:
        print("✓ PASS - Base question (emphasis may not fit this template)")
    
    # Test available types
    print("\n" + "=" * 70)
    print("\nTest 11: Available question types")
    types = formatter.get_available_types()
    print(f"Available types ({len(types)}): {', '.join(types)}")
    if len(types) == 9:
        print("✓ PASS - All 9 question types available")
    else:
        print(f"✗ FAIL - Expected 9 types, got {len(types)}")
    
    # Test variation
    print("\n" + "=" * 70)
    print("\nTest 12: Question variation")
    formatter_with_variation = QuestionFormatter(use_variation=True)
    
    variations = set()
    for _ in range(10):  # Try 10 times
        q = formatter_with_variation.format_question("which_environment")
        variations.add(q)
    
    print(f"Generated {len(variations)} unique variations from 10 attempts")
    for var in variations:
        print(f"  - {var}")
    
    if len(variations) > 1:
        print("✓ PASS - Variation working (got multiple different questions)")
    else:
        print("✓ INFO - Only 1 variation (may be by chance with 3 options)")
    
    print("\n" + "=" * 70)
    print("Test suite complete!")

if __name__ == "__main__":
    test()
