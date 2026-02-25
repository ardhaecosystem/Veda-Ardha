"""
Test suite for SAP Ontology Models
Tests all Pydantic models, validation, and helper functions.

Run with:
    cd ~/veda
    uv run python tests/test_ontology.py
"""

from datetime import datetime
from src.sap.ontology import (
    SAPSystem,
    SAPInstance,
    Host,
    Database,
    Client,
    NetworkSegment,
    TransportRoute,
    RFCDestination,
    validate_landscape_data
)


def test_sap_ontology():
    """
    Complete test suite for SAP ontology models.
    
    Tests:
    1. SAPSystem creation and validation
    2. SAPInstance creation and validation
    3. Host creation and validation
    4. Database creation and validation
    5. Client creation and validation
    6. NetworkSegment, TransportRoute, RFCDestination
    7. SID validation (reserved words, format)
    8. Instance number validation
    9. Computed properties
    10. Helper functions
    """
    
    print("=" * 70)
    print("SAP ONTOLOGY MODELS - TEST SUITE")
    print("=" * 70)
    
    # Test 1: Valid SAPSystem creation
    print("\n1. Testing SAPSystem creation...")
    try:
        system = SAPSystem(
            sid="PRD",
            system_type="S/4HANA",
            landscape_tier="PRD",
            description="Production ERP System",
            kernel_version="7.89",
            status="ACTIVE"
        )
        print(f"   ✅ Created: {system}")
        print(f"   ✅ Is production: {system.is_production}")
        
        if system.sid != "PRD":
            print(f"   ❌ SID mismatch: expected PRD, got {system.sid}")
            return False
        
        if not system.is_production:
            print(f"   ❌ is_production should be True for PRD tier")
            return False
            
    except Exception as e:
        print(f"   ❌ Failed to create SAPSystem: {e}")
        return False
    
    # Test 2: SID validation - invalid format
    print("\n2. Testing SID validation...")
    
    # Test 2a: Invalid length
    try:
        SAPSystem(sid="PRDT", system_type="S/4HANA", landscape_tier="PRD")
        print("   ❌ Should have rejected 4-character SID")
        return False
    except ValueError as e:
        print(f"   ✅ Correctly rejected 4-char SID: {str(e)[:50]}...")
    
    # Test 2b: Reserved word
    try:
        SAPSystem(sid="SAP", system_type="S/4HANA", landscape_tier="PRD")
        print("   ❌ Should have rejected reserved SID 'SAP'")
        return False
    except ValueError as e:
        print(f"   ✅ Correctly rejected reserved SID: {str(e)[:50]}...")
    
    # Test 2c: Must start with letter
    try:
        SAPSystem(sid="1AB", system_type="S/4HANA", landscape_tier="PRD")
        print("   ❌ Should have rejected SID starting with number")
        return False
    except ValueError as e:
        print(f"   ✅ Correctly rejected numeric start: {str(e)[:50]}...")
    
    # Test 2d: Auto uppercase
    try:
        system_lower = SAPSystem(sid="qas", system_type="ECC", landscape_tier="QAS")
        if system_lower.sid == "QAS":
            print(f"   ✅ Auto-uppercased 'qas' → 'QAS'")
        else:
            print(f"   ❌ Failed to uppercase: got {system_lower.sid}")
            return False
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 3: SAPInstance creation
    print("\n3. Testing SAPInstance creation...")
    try:
        instance_ascs = SAPInstance(
            instance_type="ASCS",
            instance_number="01",
            start_priority=1,
            status="GREEN"
        )
        instance_pas = SAPInstance(
            instance_type="PAS",
            instance_number="00",
            start_priority=3
        )
        
        print(f"   ✅ Created ASCS: {instance_ascs}")
        print(f"   ✅ Created PAS: {instance_pas}")
        print(f"   ✅ ASCS is central services: {instance_ascs.is_central_services}")
        print(f"   ✅ PAS is app server: {instance_pas.is_application_server}")
        
        if not instance_ascs.is_central_services:
            print("   ❌ ASCS should be central services")
            return False
        
        if not instance_pas.is_application_server:
            print("   ❌ PAS should be application server")
            return False
            
    except Exception as e:
        print(f"   ❌ Failed to create instances: {e}")
        return False
    
    # Test 4: Instance number validation
    print("\n4. Testing instance number validation...")
    
    # Test 4a: Invalid format (not 2 digits)
    try:
        SAPInstance(instance_type="PAS", instance_number="0")
        print("   ❌ Should have rejected 1-digit instance number")
        return False
    except ValueError as e:
        print(f"   ✅ Correctly rejected 1-digit: {str(e)[:50]}...")
    
    # Test 4b: Invalid format (not numeric)
    try:
        SAPInstance(instance_type="PAS", instance_number="AA")
        print("   ❌ Should have rejected non-numeric instance number")
        return False
    except ValueError as e:
        print(f"   ✅ Correctly rejected non-numeric: {str(e)[:50]}...")
    
    # Test 5: Host creation
    print("\n5. Testing Host creation...")
    try:
        host = Host(
            hostname="sap-prd-app01",
            fqdn="sap-prd-app01.company.com",
            os_type="SLES",
            os_version="15 SP5",
            ip_addresses=["10.0.1.50", "10.0.1.51"],
            cpu_cores=16,
            ram_gb=128,
            environment="on-premise"
        )
        print(f"   ✅ Created: {host}")
        
        if host.hostname != "sap-prd-app01":
            print(f"   ❌ Hostname mismatch")
            return False
            
    except Exception as e:
        print(f"   ❌ Failed to create Host: {e}")
        return False
    
    # Test 6: Hostname validation
    print("\n6. Testing hostname validation...")
    
    # Test 6a: Invalid characters
    try:
        Host(hostname="server_with_underscore")
        print("   ❌ Should have rejected underscore in hostname")
        return False
    except ValueError as e:
        print(f"   ✅ Correctly rejected underscore: {str(e)[:60]}...")
    
    # Test 6b: Auto lowercase
    try:
        host_upper = Host(hostname="SERVER01")
        if host_upper.hostname == "server01":
            print(f"   ✅ Auto-lowercased hostname")
        else:
            print(f"   ❌ Failed to lowercase: got {host_upper.hostname}")
            return False
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 7: Database creation
    print("\n7. Testing Database creation...")
    try:
        db = Database(
            db_type="HANA",
            db_sid="HDB",
            db_version="2.0 SPS07 Rev73",
            tenant_name="PRD",
            memory_allocated_gb=256
        )
        print(f"   ✅ Created: {db}")
        print(f"   ✅ Is HANA: {db.is_hana}")
        
        if not db.is_hana:
            print("   ❌ is_hana should be True")
            return False
            
    except Exception as e:
        print(f"   ❌ Failed to create Database: {e}")
        return False
    
    # Test 8: Client creation and validation
    print("\n8. Testing Client creation...")
    try:
        client = Client(
            client_number="100",
            description="Production Client",
            role="Production",
            is_production=True,
            is_open=False
        )
        print(f"   ✅ Created: {client}")
        
        # Test invalid client number
        try:
            Client(client_number="1000", description="Invalid")
            print("   ❌ Should have rejected 4-digit client number")
            return False
        except ValueError as e:
            print(f"   ✅ Correctly rejected invalid client: {str(e)[:50]}...")
            
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 9: NetworkSegment creation
    print("\n9. Testing NetworkSegment creation...")
    try:
        network = NetworkSegment(
            subnet="10.0.1.0/24",
            vlan="VLAN100",
            zone="APP",
            description="Application tier network"
        )
        print(f"   ✅ Created: {network}")
        
        # Test invalid CIDR
        try:
            NetworkSegment(subnet="invalid")
            print("   ❌ Should have rejected invalid CIDR")
            return False
        except ValueError as e:
            print(f"   ✅ Correctly rejected invalid CIDR: {str(e)[:50]}...")
            
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 10: TransportRoute creation
    print("\n10. Testing TransportRoute creation...")
    try:
        route = TransportRoute(
            route_type="Consolidation",
            description="DEV to QAS consolidation route"
        )
        print(f"   ✅ Created: {route}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 11: RFCDestination creation
    print("\n11. Testing RFCDestination creation...")
    try:
        rfc = RFCDestination(
            rfc_name="PRD_TO_BW_RFC",
            connection_type="3",
            target_client="100",
            is_trusted=True
        )
        print(f"   ✅ Created: {rfc}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 12: validate_landscape_data helper
    print("\n12. Testing validate_landscape_data helper...")
    
    test_systems = [
        {"sid": "PRD", "system_type": "S/4HANA", "landscape_tier": "PRD"},
        {"sid": "QAS", "system_type": "ECC", "landscape_tier": "QAS"},
        {"sid": "INVALID!", "system_type": "BW", "landscape_tier": "DEV"},  # Invalid
        {"sid": "DEV", "system_type": "Solution Manager", "landscape_tier": "DEV"},
    ]
    
    valid_systems, errors = validate_landscape_data(test_systems)
    
    if len(valid_systems) == 3 and len(errors) == 1:
        print(f"   ✅ Validated: {len(valid_systems)} valid, {len(errors)} errors")
        print(f"   ✅ Error message: {errors[0][:60]}...")
    else:
        print(f"   ❌ Expected 3 valid, 1 error. Got {len(valid_systems)} valid, {len(errors)} errors")
        return False
    
    # Test 13: Model serialization (to dict)
    print("\n13. Testing model serialization...")
    try:
        system_dict = system.model_dump()
        if system_dict["sid"] == "PRD" and "created_at" in system_dict:
            print(f"   ✅ Serialized to dict with {len(system_dict)} fields")
        else:
            print(f"   ❌ Serialization issue")
            return False
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 14: Edge case - all optional fields
    print("\n14. Testing minimal required fields only...")
    try:
        minimal_system = SAPSystem(
            sid="TST",  # TST is not reserved (MIN/MAX are SQL reserved words)
            system_type="ECC",
            landscape_tier="DEV"
        )
        print(f"   ✅ Created minimal system: {minimal_system}")
        
        minimal_instance = SAPInstance(
            instance_type="PAS",
            instance_number="00"
        )
        print(f"   ✅ Created minimal instance: {minimal_instance}")
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    print("\n" + "=" * 70)
    print("✅ ALL ONTOLOGY TESTS PASSED!")
    print("=" * 70)
    print("\nSAP Ontology Models are production-ready!")
    print("Next step: Create src/sap/port_calculator.py\n")
    
    return True


if __name__ == "__main__":
    success = test_sap_ontology()
    exit(0 if success else 1)
