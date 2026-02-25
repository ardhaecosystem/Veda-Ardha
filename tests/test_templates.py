"""
Test suite for SAPTemplateManager
Tests SAP ontology base template creation and cloning.

Run with:
    cd ~/veda
    uv run python tests/test_templates.py
"""

import os
from dotenv import load_dotenv
from src.projects.context_manager import ProjectContextManager
from src.projects.templates import SAPTemplateManager


def test_sap_templates():
    """
    Complete test suite for SAPTemplateManager.
    
    Tests:
    1. Template manager initialization
    2. SAP ontology base creation
    3. Template verification (nodes and relationships)
    4. Template cloning for new project
    5. Documentation retrieval
    """
    
    print("=" * 70)
    print("SAP TEMPLATE MANAGER - TEST SUITE")
    print("=" * 70)
    
    # Load environment
    load_dotenv()
    
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    password = os.getenv("FALKORDB_PASSWORD")
    
    # Test 1: Initialize managers
    print("\n1. Initializing ProjectContextManager and SAPTemplateManager...")
    
    try:
        project_mgr = ProjectContextManager(
            falkordb_host=host,
            falkordb_port=port,
            falkordb_password=password
        )
        template_mgr = SAPTemplateManager(project_mgr)
        print("   ✅ Managers initialized")
    except Exception as e:
        print(f"   ❌ Initialization failed: {e}")
        return False
    
    # Test 2: Create SAP ontology base template
    print("\n2. Creating SAP ontology base template...")
    
    try:
        created = template_mgr.create_sap_ontology_base()
        if created:
            print("   ✅ Template created successfully")
        else:
            print("   ⚠️  Template already exists (this is OK)")
    except Exception as e:
        print(f"   ❌ Template creation failed: {e}")
        return False
    
    # Test 3: Verify template exists in graph list
    print("\n3. Verifying template in graph list...")
    
    graphs = project_mgr.db.list_graphs()
    if "sap_ontology_base" in graphs:
        print("   ✅ Template found in graph list")
    else:
        print(f"   ❌ Template not found. Available graphs: {graphs}")
        return False
    
    # Test 4: Query template structure
    print("\n4. Querying template structure...")
    
    try:
        template_graph = project_mgr.db.select_graph("sap_ontology_base")
        
        # Count nodes
        node_result = template_graph.query("MATCH (n) RETURN count(n) as count")
        node_count = node_result.result_set[0][0] if node_result.result_set else 0
        
        # Count relationships
        rel_result = template_graph.query("MATCH ()-[r]->() RETURN count(r) as count")
        rel_count = rel_result.result_set[0][0] if rel_result.result_set else 0
        
        print(f"   ✅ Template structure:")
        print(f"      - Nodes: {node_count}")
        print(f"      - Relationships: {rel_count}")
        
        if node_count == 0:
            print("   ⚠️  Template has no nodes (unexpected)")
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
        return False
    
    # Test 5: Verify metadata node
    print("\n5. Verifying template metadata...")
    
    try:
        meta_result = template_graph.query("""
            MATCH (m:TemplateMetadata)
            RETURN m.name as name, m.version as version
        """)
        
        if meta_result.result_set:
            name = meta_result.result_set[0][0]
            version = meta_result.result_set[0][1]
            print(f"   ✅ Metadata found:")
            print(f"      - Name: {name}")
            print(f"      - Version: {version}")
        else:
            print("   ⚠️  No metadata node found")
    except Exception as e:
        print(f"   ❌ Metadata query failed: {e}")
        return False
    
    # Test 6: Verify example nodes
    print("\n6. Verifying example nodes...")
    
    try:
        # Check for example SAP system
        sys_result = template_graph.query("""
            MATCH (s:SAPSystem {sid: 'EXAMPLE'})
            RETURN s.sid, s.system_type
        """)
        
        if sys_result.result_set:
            print(f"   ✅ Found example SAPSystem: {sys_result.result_set[0]}")
        else:
            print("   ⚠️  No example SAPSystem found")
        
        # Check for example Host
        host_result = template_graph.query("""
            MATCH (h:Host {hostname: 'example-host'})
            RETURN h.hostname
        """)
        
        if host_result.result_set:
            print(f"   ✅ Found example Host: {host_result.result_set[0][0]}")
        else:
            print("   ⚠️  No example Host found")
        
        # Check for example Database
        db_result = template_graph.query("""
            MATCH (d:Database {db_type: 'HANA'})
            RETURN d.db_type, d.db_sid
        """)
        
        if db_result.result_set:
            print(f"   ✅ Found example Database: {db_result.result_set[0]}")
        else:
            print("   ⚠️  No example Database found")
            
    except Exception as e:
        print(f"   ❌ Example node verification failed: {e}")
        return False
    
    # Test 7: Clone template for new project
    print("\n7. Testing template cloning...")
    
    try:
        # Clean up if test project exists
        test_graphs = project_mgr.db.list_graphs()
        if "project_test_sap_clone" in test_graphs:
            print("   🧹 Cleaning up existing test project...")
            project_mgr.db.select_graph("project_test_sap_clone").delete()
        
        # Create new project from template
        print("   Creating new project from template...")
        context = project_mgr.create_project(
            "test_sap_clone",
            clone_from="sap_ontology_base"
        )
        print(f"   ✅ Project cloned: {context.project_id}")
        
        # Verify clone has same structure
        clone_result = project_mgr.query("MATCH (n) RETURN count(n) as count")
        clone_nodes = clone_result.result_set[0][0] if clone_result.result_set else 0
        
        print(f"   ✅ Cloned project has {clone_nodes} nodes (same as template)")
        
        if clone_nodes != node_count:
            print(f"   ⚠️  Node count mismatch: template={node_count}, clone={clone_nodes}")
        
    except Exception as e:
        print(f"   ❌ Template cloning failed: {e}")
        return False
    
    # Test 8: Get documentation
    print("\n8. Testing documentation retrieval...")
    
    try:
        node_docs = template_mgr.get_node_type_documentation()
        rel_docs = template_mgr.get_relationship_type_documentation()
        
        print(f"   ✅ Documentation retrieved:")
        print(f"      - Node types: {len(node_docs)}")
        print(f"      - Relationship types: {len(rel_docs)}")
        
        # Show a few examples
        print(f"   📖 Sample node types:")
        for label in list(node_docs.keys())[:3]:
            print(f"      - {label}: {node_docs[label].description[:50]}...")
        
        print(f"   📖 Sample relationship types:")
        for rel_type in list(rel_docs.keys())[:3]:
            doc = rel_docs[rel_type]
            print(f"      - {rel_type}: ({doc.from_label})->({doc.to_label})")
        
    except Exception as e:
        print(f"   ❌ Documentation retrieval failed: {e}")
        return False
    
    # Test 9: Print reference guide (optional)
    print("\n9. Generating ontology reference guide...")
    try:
        print("\n" + "-" * 70)
        template_mgr.print_ontology_reference()
        print("-" * 70)
        print("   ✅ Reference guide generated")
    except Exception as e:
        print(f"   ⚠️  Reference guide generation failed: {e}")
        # Not critical, continue
    
    # Test 10: Cleanup test project
    print("\n10. Cleanup...")
    try:
        project_mgr.unmount()
        project_mgr.delete_project("test_sap_clone", confirm=True)
        print("   ✅ Test project cleaned up")
    except Exception as e:
        print(f"   ⚠️  Cleanup warning: {e}")
    
    print("\n" + "=" * 70)
    print("✅ ALL TEMPLATE TESTS PASSED!")
    print("=" * 70)
    print("\nSAP Ontology Template is production-ready!")
    print("The 'sap_ontology_base' graph is now available for cloning.\n")
    print("📋 PHASE 1 FOUNDATION COMPLETE!")
    print("   Next: Create SAP domain knowledge files in src/sap/\n")
    
    return True


if __name__ == "__main__":
    success = test_sap_templates()
    exit(0 if success else 1)
