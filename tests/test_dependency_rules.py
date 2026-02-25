"""
Test suite for SAP Dependency Rules
Tests startup sequences, dependency validation, and troubleshooting helpers.

Run with:
    cd ~/veda
    uv run python tests/test_dependency_rules.py
"""

from src.sap.dependency_rules import (
    DependencyValidator,
    DependencyRule,
    StartupSequence,
    StartupPriority,
    get_standard_startup_sequence,
    create_troubleshooting_guide
)


def test_dependency_rules():
    """
    Complete test suite for SAP dependency rules.
    
    Tests:
    1. Startup priority assignment
    2. Dependency rule checking
    3. Can-start validation
    4. Startup sequence generation
    5. Shutdown sequence generation
    6. Multi-stage sequences
    7. Missing dependency detection
    8. Circular dependency detection
    9. Startup failure explanations
    10. Troubleshooting guide generation
    """
    
    print("=" * 70)
    print("SAP DEPENDENCY RULES - TEST SUITE")
    print("=" * 70)
    
    # Initialize validator
    validator = DependencyValidator()
    
    # Test 1: Startup priority assignment
    print("\n1. Testing startup priority assignment...")
    
    hdb_priority = validator.get_startup_priority("HDB")
    ascs_priority = validator.get_startup_priority("ASCS")
    pas_priority = validator.get_startup_priority("PAS")
    aas_priority = validator.get_startup_priority("AAS")
    
    print(f"   ✅ Priorities assigned correctly:")
    print(f"      HDB: {hdb_priority} (DATABASE)")
    print(f"      ASCS: {ascs_priority} (CENTRAL_SERVICES)")
    print(f"      PAS: {pas_priority} (PRIMARY_APP)")
    print(f"      AAS: {aas_priority} (ADDITIONAL_APP)")
    
    if not (hdb_priority < ascs_priority < pas_priority < aas_priority):
        print("   ❌ Priority ordering incorrect")
        return False
    
    # Test 2: Get dependencies for instance type
    print("\n2. Testing dependency retrieval...")
    
    pas_deps = validator.get_dependencies("PAS", critical_only=True)
    print(f"   ✅ PAS has {len(pas_deps)} critical dependencies:")
    
    for dep in pas_deps:
        print(f"      - {dep.required} ({dep.dependency_type})")
    
    if len(pas_deps) != 2:  # Should depend on HDB and ASCS
        print(f"   ❌ Expected 2 dependencies, got {len(pas_deps)}")
        return False
    
    # Test 3: Can-start validation (positive case)
    print("\n3. Testing can-start validation (positive)...")
    
    can_start, missing = validator.check_can_start("PAS", ["HDB", "ASCS"])
    
    if can_start and len(missing) == 0:
        print("   ✅ PAS can start when HDB and ASCS are running")
    else:
        print(f"   ❌ PAS should be able to start. Missing: {missing}")
        return False
    
    # Test 4: Can-start validation (negative case)
    print("\n4. Testing can-start validation (negative)...")
    
    can_start, missing = validator.check_can_start("PAS", ["HDB"])
    
    if not can_start and "ASCS" in missing:
        print("   ✅ Correctly detected PAS cannot start without ASCS")
        print(f"      Missing dependencies: {missing}")
    else:
        print("   ❌ Should have detected missing ASCS")
        return False
    
    # Test 5: Simple startup sequence
    print("\n5. Testing simple startup sequence generation...")
    
    simple_system = {
        "HDB00": "HDB",
        "ASCS01": "ASCS",
        "PAS00": "PAS"
    }
    
    sequence = validator.generate_startup_sequence(simple_system)
    
    print(f"   ✅ Generated sequence with {len(sequence.sequence)} stages:")
    for i, stage in enumerate(sequence.sequence, 1):
        print(f"      Stage {i}: {', '.join(stage)}")
    
    # Verify order: HDB before ASCS before PAS
    flat_order = sequence.get_flat_order()
    hdb_idx = flat_order.index("HDB00")
    ascs_idx = flat_order.index("ASCS01")
    pas_idx = flat_order.index("PAS00")
    
    if not (hdb_idx < ascs_idx < pas_idx):
        print(f"   ❌ Incorrect order: {flat_order}")
        return False
    
    # Test 6: Complex system with parallel stages
    print("\n6. Testing complex system with multiple AAS...")
    
    complex_system = {
        "HDB00": "HDB",
        "ASCS01": "ASCS",
        "ERS02": "ERS",
        "PAS00": "PAS",
        "AAS10": "AAS",
        "AAS11": "AAS",
        "AAS12": "AAS"
    }
    
    complex_sequence = validator.generate_startup_sequence(complex_system)
    
    print(f"   ✅ Generated sequence with {len(complex_sequence.sequence)} stages:")
    for i, stage in enumerate(complex_sequence.sequence, 1):
        print(f"      Stage {i}: {', '.join(stage)}")
    
    # Check that all 3 AAS instances are in the same stage (can start in parallel)
    aas_stages = [
        complex_sequence.get_stage_for_instance("AAS10"),
        complex_sequence.get_stage_for_instance("AAS11"),
        complex_sequence.get_stage_for_instance("AAS12")
    ]
    
    if len(set(aas_stages)) == 1:
        print(f"   ✅ All AAS instances in same stage {aas_stages[0]} (parallel startup)")
    else:
        print(f"   ❌ AAS instances in different stages: {aas_stages}")
        return False
    
    # Test 7: Shutdown sequence (reverse of startup)
    print("\n7. Testing shutdown sequence generation...")
    
    shutdown = validator.generate_shutdown_sequence(simple_system)
    
    print(f"   ✅ Generated shutdown sequence:")
    for i, stage in enumerate(shutdown.sequence, 1):
        print(f"      Stage {i}: {', '.join(stage)}")
    
    # Verify reverse order: PAS before ASCS before HDB
    shutdown_flat = shutdown.get_flat_order()
    pas_shutdown_idx = shutdown_flat.index("PAS00")
    ascs_shutdown_idx = shutdown_flat.index("ASCS01")
    hdb_shutdown_idx = shutdown_flat.index("HDB00")
    
    if not (pas_shutdown_idx < ascs_shutdown_idx < hdb_shutdown_idx):
        print(f"   ❌ Incorrect shutdown order: {shutdown_flat}")
        return False
    
    # Test 8: Validation warnings
    print("\n8. Testing validation warnings...")
    
    # System without database
    incomplete_system = {
        "ASCS01": "ASCS",
        "PAS00": "PAS"
    }
    
    incomplete_sequence = validator.generate_startup_sequence(incomplete_system)
    
    if len(incomplete_sequence.warnings) > 0:
        print(f"   ✅ Detected {len(incomplete_sequence.warnings)} warning(s):")
        for warning in incomplete_sequence.warnings:
            print(f"      - {warning}")
    else:
        print("   ❌ Should have warned about missing database")
        return False
    
    # Test 9: Explain startup failure
    print("\n9. Testing startup failure explanation...")
    
    explanation = validator.explain_startup_failure("PAS", ["HDB"])
    
    if "ASCS" in explanation and "cannot start" in explanation:
        print("   ✅ Generated helpful explanation:")
        print("      " + explanation.split("\n")[0])
        print("      " + explanation.split("\n")[2][:60] + "...")
    else:
        print("   ❌ Explanation missing key information")
        return False
    
    # Test 10: Circular dependency detection
    print("\n10. Testing circular dependency detection...")
    
    cycles = validator.detect_circular_dependencies()
    
    if len(cycles) == 0:
        print("   ✅ No circular dependencies detected (correct)")
    else:
        print(f"   ❌ Unexpected circular dependencies: {cycles}")
        return False
    
    # Test 11: Get stage for instance
    print("\n11. Testing get_stage_for_instance helper...")
    
    pas_stage = sequence.get_stage_for_instance("PAS00")
    hdb_stage = sequence.get_stage_for_instance("HDB00")
    nonexistent_stage = sequence.get_stage_for_instance("NONEXISTENT")
    
    if pas_stage is not None and hdb_stage is not None and nonexistent_stage is None:
        print(f"   ✅ Stage lookup working:")
        print(f"      PAS00 in stage {pas_stage}")
        print(f"      HDB00 in stage {hdb_stage}")
        print(f"      NONEXISTENT returns None: {nonexistent_stage is None}")
    else:
        print("   ❌ Stage lookup failed")
        return False
    
    # Test 12: Standard startup sequence reference
    print("\n12. Testing standard startup sequence helper...")
    
    standard = get_standard_startup_sequence()
    
    if len(standard) >= 5:
        print(f"   ✅ Standard sequence has {len(standard)} steps:")
        for priority, inst_type, desc in standard[:3]:
            print(f"      {priority}. {inst_type}: {desc}")
    else:
        print("   ❌ Standard sequence incomplete")
        return False
    
    # Test 13: Troubleshooting guide generation
    print("\n13. Testing troubleshooting guide generation...")
    
    guide = create_troubleshooting_guide("PAS")
    
    if "Prerequisites" in guide and "ASCS" in guide and "HDB" in guide:
        print("   ✅ Generated troubleshooting guide:")
        lines = guide.split("\n")
        print(f"      Title: {lines[0]}")
        print(f"      Length: {len(lines)} lines")
        print(f"      Contains prerequisites: ✓")
    else:
        print("   ❌ Troubleshooting guide incomplete")
        return False
    
    # Test 14: Edge case - ASCS can start with just DB
    print("\n14. Testing ASCS startup requirements...")
    
    can_start, missing = validator.check_can_start("ASCS", ["HDB"])
    
    if can_start:
        print("   ✅ ASCS can start with only HDB running (correct)")
    else:
        print(f"   ❌ ASCS should be able to start with HDB. Missing: {missing}")
        return False
    
    # Test 15: Edge case - AAS requires both ASCS and PAS (soft)
    print("\n15. Testing AAS startup requirements...")
    
    aas_deps = validator.get_dependencies("AAS", critical_only=False)
    
    critical_deps = [d.required for d in aas_deps if d.is_critical]
    soft_deps = [d.required for d in aas_deps if not d.is_critical]
    
    print(f"   ✅ AAS dependencies:")
    print(f"      Critical: {critical_deps}")
    print(f"      Soft: {soft_deps}")
    
    if "HDB" in critical_deps and "ASCS" in critical_deps:
        print("   ✅ AAS has correct critical dependencies")
    else:
        print("   ❌ AAS missing critical dependencies")
        return False
    
    print("\n" + "=" * 70)
    print("✅ ALL DEPENDENCY RULES TESTS PASSED!")
    print("=" * 70)
    print("\nSAP Dependency Rules are production-ready!")
    print("Next step: Create src/sap/validators.py\n")
    
    return True


if __name__ == "__main__":
    success = test_dependency_rules()
    exit(0 if success else 1)
