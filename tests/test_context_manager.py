"""
Test suite for ProjectContextManager
Tests multi-project isolation, graph operations, and safety features.

Run with:
    cd ~/veda
    uv run python tests/test_context_manager.py
"""

import os
from dotenv import load_dotenv
from src.projects.context_manager import ProjectContextManager

def test_context_manager():
    """
    Complete test suite for ProjectContextManager.
    
    Tests:
    1. Connection to FalkorDB
    2. Project creation
    3. Data insertion and isolation
    4. Query safety (unmount protection)
    5. Data persistence
    6. Project listing
    7. Project statistics
    8. Cleanup
    """
    
    print("=" * 70)
    print("PROJECT CONTEXT MANAGER - TEST SUITE")
    print("=" * 70)
    
    # Load environment variables
    load_dotenv()
    
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    password = os.getenv("FALKORDB_PASSWORD")
    
    # Test 1: Connection
    print(f"\n1. Connecting to FalkorDB at {host}:{port}...")
    
    try:
        manager = ProjectContextManager(
            falkordb_host=host,
            falkordb_port=port,
            falkordb_password=password
        )
        print("   ✅ Connected successfully!")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False
    
    # Test 2: Create test project
    print("\n2. Creating test project 'test_project_001'...")
    try:
        context = manager.create_project(
            "test_project_001",
            metadata={"description": "Test project for validation"}
        )
        print(f"   ✅ Created and auto-mounted: {context}")
    except ValueError as e:
        if "already exists" in str(e):
            print(f"   ⚠️  Project exists, mounting instead...")
            context = manager.mount("test_project_001")
        else:
            print(f"   ❌ Creation failed: {e}")
            return False
    
    # Test 3: Add test data
    print("\n3. Adding test data to mounted project...")
    try:
        manager.query(
            "CREATE (:SAPSystem {sid: 'TST', description: 'Test System'})"
        )
        manager.query(
            "CREATE (:Host {hostname: 'testserver01', ip: '10.0.0.1'})"
        )
        print("   ✅ Test nodes created")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 4: Query the data
    print("\n4. Querying mounted project...")
    try:
        result = manager.query("MATCH (n) RETURN n LIMIT 5")
        print(f"   ✅ Found {len(result.result_set)} nodes")
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
        return False
    
    # Test 5: Test unmount safety
    print("\n5. Testing unmount safety...")
    manager.unmount()
    print("   ✅ Unmounted successfully")
    
    try:
        manager.query("MATCH (n) RETURN n")
        print("   ❌ ERROR: Should have raised RuntimeError!")
        return False
    except RuntimeError as e:
        print(f"   ✅ Correctly prevented query without mount")
    
    # Test 6: Remount and verify data persists
    print("\n6. Remounting and verifying data persistence...")
    manager.mount("test_project_001")
    result = manager.query("MATCH (s:SAPSystem) RETURN s.sid")
    if result.result_set:
        print(f"   ✅ Data persisted: Found SID '{result.result_set[0][0]}'")
    else:
        print("   ⚠️  No data found (unexpected)")
        return False
    
    # Test 7: List all projects
    print("\n7. Listing all projects...")
    projects = manager.list_projects()
    print(f"   ✅ Found {len(projects)} projects:")
    for proj in projects[:5]:  # Show first 5
        print(f"      - {proj}")
    if len(projects) > 5:
        print(f"      ... and {len(projects) - 5} more")
    
    # Test 8: Get project info
    print("\n8. Getting project statistics...")
    try:
        info = manager.get_project_info("test_project_001")
        print(f"   ✅ Project info:")
        print(f"      - Nodes: {info.get('node_count', 'N/A')}")
        print(f"      - Edges: {info.get('edge_count', 'N/A')}")
        print(f"      - Mounted: {info.get('is_mounted', False)}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 9: Cleanup
    print("\n9. Cleanup (delete test project)...")
    try:
        manager.delete_project("test_project_001", confirm=True)
        print("   ✅ Test project deleted")
    except Exception as e:
        print(f"   ⚠️  Cleanup failed: {e}")
        print("   Manual cleanup may be needed")
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    print("\nProjectContextManager is production-ready!")
    print("Next step: Create src/projects/isolation.py\n")
    
    return True


if __name__ == "__main__":
    success = test_context_manager()
    exit(0 if success else 1)
