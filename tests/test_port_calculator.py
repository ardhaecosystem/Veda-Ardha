"""
Test suite for SAP Port Calculator
Tests all port formulas, conflict detection, and utilities.

Run with:
    cd ~/veda
    uv run python tests/test_port_calculator.py
"""

from src.sap.port_calculator import (
    calculate_dispatcher_port,
    calculate_gateway_port,
    calculate_message_server_port,
    calculate_http_port,
    calculate_https_port,
    calculate_hana_sql_port,
    calculate_hana_systemdb_port,
    calculate_instance_ports,
    extract_instance_from_port,
    detect_port_conflicts,
    is_sap_standard_port,
    calculate_system_ports,
    get_port_summary
)


def test_port_calculator():
    """
    Complete test suite for SAP port calculator.
    
    Tests:
    1. Individual port formula calculations
    2. HANA port calculations (3NN15 pattern)
    3. Comprehensive instance port calculation
    4. Reverse calculation (port → instance)
    5. Port conflict detection
    6. Standard port recognition
    7. Batch operations
    8. Port summary generation
    """
    
    print("=" * 70)
    print("SAP PORT CALCULATOR - TEST SUITE")
    print("=" * 70)
    
    # Test 1: Dispatcher port formula (32NN)
    print("\n1. Testing dispatcher port calculation...")
    port_00 = calculate_dispatcher_port("00")
    port_10 = calculate_dispatcher_port("10")
    port_99 = calculate_dispatcher_port("99")
    
    if port_00 == 3200 and port_10 == 3210 and port_99 == 3299:
        print(f"   ✅ Dispatcher ports: 00={port_00}, 10={port_10}, 99={port_99}")
    else:
        print(f"   ❌ Dispatcher calculation error")
        return False
    
    # Test 2: Gateway port formula (33NN)
    print("\n2. Testing gateway port calculation...")
    gw_00 = calculate_gateway_port("00")
    gw_01 = calculate_gateway_port("01")
    
    if gw_00 == 3300 and gw_01 == 3301:
        print(f"   ✅ Gateway ports: 00={gw_00}, 01={gw_01}")
    else:
        print(f"   ❌ Gateway calculation error")
        return False
    
    # Test 3: Message Server port formula (36NN)
    print("\n3. Testing message server port calculation...")
    ms_00 = calculate_message_server_port("00")
    ms_01 = calculate_message_server_port("01")
    
    if ms_00 == 3600 and ms_01 == 3601:
        print(f"   ✅ Message Server ports: 00={ms_00}, 01={ms_01}")
    else:
        print(f"   ❌ Message Server calculation error")
        return False
    
    # Test 4: HTTP/HTTPS ports
    print("\n4. Testing HTTP/HTTPS port calculation...")
    http_00 = calculate_http_port("00")
    https_00 = calculate_https_port("00")
    
    if http_00 == 8000 and https_00 == 44300:
        print(f"   ✅ HTTP={http_00}, HTTPS={https_00}")
    else:
        print(f"   ❌ HTTP/HTTPS calculation error")
        return False
    
    # Test 5: HANA port formulas (3NN15, 3NN13, 3NN03)
    print("\n5. Testing HANA port calculations...")
    hana_sql_00 = calculate_hana_sql_port("00")
    hana_sql_10 = calculate_hana_sql_port("10")
    hana_systemdb_00 = calculate_hana_systemdb_port("00")
    
    expected_sql_00 = 30015
    expected_sql_10 = 31015  # 30015 + 10*100
    expected_sysdb = 30013
    
    if (hana_sql_00 == expected_sql_00 and 
        hana_sql_10 == expected_sql_10 and 
        hana_systemdb_00 == expected_sysdb):
        print(f"   ✅ HANA SQL: 00={hana_sql_00}, 10={hana_sql_10}")
        print(f"   ✅ HANA System DB: 00={hana_systemdb_00}")
    else:
        print(f"   ❌ HANA calculation error")
        print(f"      Got: SQL00={hana_sql_00}, SQL10={hana_sql_10}, SysDB={hana_systemdb_00}")
        print(f"      Expected: {expected_sql_00}, {expected_sql_10}, {expected_sysdb}")
        return False
    
    # Test 6: Comprehensive instance port calculation - PAS
    print("\n6. Testing comprehensive PAS instance ports...")
    pas_ports = calculate_instance_ports("00", "PAS")
    
    if (pas_ports.dispatcher == 3200 and 
        pas_ports.gateway == 3300 and
        pas_ports.message_server == 3600 and
        pas_ports.http == 8000 and
        pas_ports.https == 44300):
        print(f"   ✅ PAS00 complete port set calculated")
        print(f"      Dispatcher: {pas_ports.dispatcher}")
        print(f"      Gateway: {pas_ports.gateway}")
        print(f"      Message Server: {pas_ports.message_server}")
        print(f"      HTTP: {pas_ports.http}")
        print(f"      HTTPS: {pas_ports.https}")
    else:
        print(f"   ❌ PAS port calculation incomplete")
        return False
    
    # Test 7: ASCS instance ports
    print("\n7. Testing ASCS instance ports...")
    ascs_ports = calculate_instance_ports("01", "ASCS")
    
    if (ascs_ports.message_server == 3601 and 
        ascs_ports.enqueue == 3201 and
        ascs_ports.gateway == 3301):
        print(f"   ✅ ASCS01 ports calculated correctly")
        print(f"      Message Server: {ascs_ports.message_server}")
        print(f"      Enqueue: {ascs_ports.enqueue}")
    else:
        print(f"   ❌ ASCS port calculation error")
        return False
    
    # Test 8: HDB instance ports
    print("\n8. Testing HANA (HDB) instance ports...")
    hdb_ports = calculate_instance_ports("00", "HDB")
    
    if (hdb_ports.hana_sql == 30015 and 
        hdb_ports.hana_systemdb == 30013 and
        hdb_ports.hana_indexserver == 30003):
        print(f"   ✅ HDB00 ports calculated correctly")
        print(f"      SQL: {hdb_ports.hana_sql}")
        print(f"      System DB: {hdb_ports.hana_systemdb}")
        print(f"      Index Server: {hdb_ports.hana_indexserver}")
    else:
        print(f"   ❌ HDB port calculation error")
        return False
    
    # Test 9: Reverse calculation (port → instance)
    print("\n9. Testing reverse calculation (port → instance)...")
    
    instance_from_disp = extract_instance_from_port(3210, "dispatcher")
    instance_from_gw = extract_instance_from_port(3301, "gateway")
    instance_from_hana = extract_instance_from_port(31015, "hana_sql")
    
    if (instance_from_disp == "10" and 
        instance_from_gw == "01" and
        instance_from_hana == "10"):
        print(f"   ✅ Reverse calculation working")
        print(f"      Port 3210 (dispatcher) → Instance {instance_from_disp}")
        print(f"      Port 3301 (gateway) → Instance {instance_from_gw}")
        print(f"      Port 31015 (HANA SQL) → Instance {instance_from_hana}")
    else:
        print(f"   ❌ Reverse calculation error")
        return False
    
    # Test 10: Port conflict detection
    print("\n10. Testing port conflict detection...")
    
    # Create conflicting instances (both using instance 00)
    conflicting_instances = [
        {"instance_number": "00", "instance_type": "PAS"},
        {"instance_number": "00", "instance_type": "ASCS"}
    ]
    
    conflicts = detect_port_conflicts(conflicting_instances)
    
    if len(conflicts) > 0:
        print(f"   ✅ Detected {len(conflicts)} port conflicts (expected)")
        print(f"      Example conflict: Port {conflicts[0]['port']}")
        print(f"        {conflicts[0]['instance_1']} ({conflicts[0]['port_name_1']})")
        print(f"        vs {conflicts[0]['instance_2']} ({conflicts[0]['port_name_2']})")
    else:
        print(f"   ❌ Should have detected conflicts")
        return False
    
    # Test 11: No conflicts scenario
    print("\n11. Testing non-conflicting instances...")
    
    non_conflicting = [
        {"instance_number": "00", "instance_type": "PAS"},
        {"instance_number": "01", "instance_type": "ASCS"}
    ]
    
    conflicts_none = detect_port_conflicts(non_conflicting)
    
    if len(conflicts_none) == 0:
        print(f"   ✅ No conflicts detected (correct)")
    else:
        print(f"   ❌ False positive: detected conflicts where none exist")
        return False
    
    # Test 12: Standard port recognition
    print("\n12. Testing standard port recognition...")
    
    std_3200 = is_sap_standard_port(3200)
    std_30015 = is_sap_standard_port(30015)
    std_random = is_sap_standard_port(12345)
    
    if (std_3200 and "Dispatcher" in std_3200 and
        std_30015 and "HANA SQL" in std_30015 and
        std_random is None):
        print(f"   ✅ Standard port recognition working")
        print(f"      3200: {std_3200}")
        print(f"      30015: {std_30015}")
        print(f"      12345: Not standard (correct)")
    else:
        print(f"   ❌ Standard port recognition error")
        return False
    
    # Test 13: Batch system port calculation
    print("\n13. Testing batch system port calculation...")
    
    system_instances = [
        {"instance_number": "01", "instance_type": "ASCS"},
        {"instance_number": "00", "instance_type": "PAS"},
        {"instance_number": "10", "instance_type": "AAS"},
        {"instance_number": "00", "instance_type": "HDB"}
    ]
    
    system_ports = calculate_system_ports(system_instances)
    
    if len(system_ports) == 4:
        print(f"   ✅ Calculated ports for {len(system_ports)} instances")
        print(f"      Instance IDs: {', '.join(system_ports.keys())}")
        
        # Verify we can access ports
        if "PAS00" in system_ports:
            pas_disp = system_ports["PAS00"].dispatcher
            print(f"      PAS00 dispatcher: {pas_disp}")
    else:
        print(f"   ❌ System port calculation error")
        return False
    
    # Test 14: Port summary generation
    print("\n14. Testing port summary generation...")
    
    try:
        summary = get_port_summary(system_instances)
        
        if "ASCS01" in summary and "PAS00" in summary and "dispatcher" in summary:
            print(f"   ✅ Port summary generated")
            print(f"      Summary length: {len(summary)} characters")
            print(f"      Contains expected instance IDs and port names")
        else:
            print(f"   ❌ Port summary incomplete")
            return False
    except Exception as e:
        print(f"   ❌ Summary generation failed: {e}")
        return False
    
    # Test 15: InstancePorts helper methods
    print("\n15. Testing InstancePorts helper methods...")
    
    ports = calculate_instance_ports("00", "PAS")
    all_ports = ports.get_all_ports()
    ports_dict = ports.to_dict()
    
    if len(all_ports) > 0 and isinstance(ports_dict, dict):
        print(f"   ✅ Helper methods working")
        print(f"      get_all_ports(): {len(all_ports)} ports")
        print(f"      to_dict(): {len(ports_dict)} entries")
    else:
        print(f"   ❌ Helper methods error")
        return False
    
    print("\n" + "=" * 70)
    print("✅ ALL PORT CALCULATOR TESTS PASSED!")
    print("=" * 70)
    print("\nSAP Port Calculator is production-ready!")
    print("Next step: Create src/sap/dependency_rules.py\n")
    
    return True


if __name__ == "__main__":
    success = test_port_calculator()
    exit(0 if success else 1)
