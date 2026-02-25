"""
Test Suite for Query Builder (Phase 2, Layer 3)

Tests safe query construction and injection prevention.
"""

import pytest
from src.sap.query_builder import (
    QueryBuilder,
    QueryValidator,
    RelationshipDirection,
    SAPQueryTemplates,
    build_safe_query
)


class TestQueryValidator:
    """Test query validation and whitelisting."""
    
    def test_valid_label_accepted(self):
        """Valid labels should pass."""
        assert QueryValidator.validate_label("SAPSystem")
        assert QueryValidator.validate_label("SAPInstance")
        assert QueryValidator.validate_label("Host")
    
    def test_invalid_label_rejected(self):
        """Invalid labels should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid node label"):
            QueryValidator.validate_label("MaliciousNode")
        
        with pytest.raises(ValueError, match="Invalid node label"):
            QueryValidator.validate_label("'; DROP TABLE users; --")
    
    def test_valid_relationship_accepted(self):
        """Valid relationship types should pass."""
        assert QueryValidator.validate_relationship("HAS_INSTANCE")
        assert QueryValidator.validate_relationship("RUNS_ON")
        assert QueryValidator.validate_relationship("DEPENDS_ON")
    
    def test_invalid_relationship_rejected(self):
        """Invalid relationships should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid relationship type"):
            QueryValidator.validate_relationship("MALICIOUS_REL")
        
        with pytest.raises(ValueError, match="Invalid relationship type"):
            QueryValidator.validate_relationship("'; DROP GRAPH; --")
    
    def test_valid_property_accepted(self):
        """Valid property names should pass."""
        assert QueryValidator.validate_property("sid")
        assert QueryValidator.validate_property("instance_number")
        assert QueryValidator.validate_property("hostname")
    
    def test_invalid_property_rejected(self):
        """Invalid properties should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid property name"):
            QueryValidator.validate_property("malicious_prop")
        
        with pytest.raises(ValueError, match="Invalid property name"):
            QueryValidator.validate_property("'; DROP TABLE; --")
    
    def test_valid_param_name_accepted(self):
        """Valid parameter names should pass."""
        assert QueryValidator.validate_param_name("param_1")
        assert QueryValidator.validate_param_name("_private_param")
        assert QueryValidator.validate_param_name("SID123")
    
    def test_invalid_param_name_rejected(self):
        """Invalid parameter names should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid parameter name"):
            QueryValidator.validate_param_name("param-with-dash")
        
        with pytest.raises(ValueError, match="Invalid parameter name"):
            QueryValidator.validate_param_name("123_starts_with_number")
        
        with pytest.raises(ValueError, match="Invalid parameter name"):
            QueryValidator.validate_param_name("'; malicious")


class TestQueryBuilder:
    """Test query builder functionality."""
    
    def test_simple_match_query(self):
        """Build simple MATCH query with properties."""
        builder = QueryBuilder()
        result = builder.match_nodes("SAPSystem", {"sid": "PRD"}).return_nodes().build()
        
        assert "MATCH (n:SAPSystem" in result.query
        assert "sid: $sid_1" in result.query
        assert "RETURN n" in result.query
        assert result.parameters["sid_1"] == "PRD"
    
    def test_match_without_properties(self):
        """Build MATCH query without filters."""
        builder = QueryBuilder()
        result = builder.match_nodes("SAPSystem").return_nodes().build()
        
        assert "MATCH (n:SAPSystem)" in result.query
        assert "RETURN n" in result.query
        assert len(result.parameters) == 0
    
    def test_custom_alias(self):
        """Use custom node alias."""
        builder = QueryBuilder()
        result = builder.match_nodes("SAPSystem", {"sid": "QAS"}, alias="sys").return_nodes().build()
        
        assert "(sys:SAPSystem" in result.query
        assert "RETURN sys" in result.query
    
    def test_relationship_traversal_outgoing(self):
        """Traverse outgoing relationship."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", {"sid": "PRD"}, alias="sys") \
            .match_relationship("HAS_INSTANCE", "SAPInstance", 
                              source_alias="sys", target_alias="inst") \
            .return_nodes(["sys", "inst"]) \
            .build()
        
        assert "MATCH (sys:SAPSystem" in result.query
        assert "(sys)-[r:HAS_INSTANCE]->(inst:SAPInstance)" in result.query
        assert "RETURN sys, inst" in result.query
    
    def test_relationship_traversal_incoming(self):
        """Traverse incoming relationship."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("Host", {"hostname": "server01"}, alias="host") \
            .match_relationship("HOSTED_ON", "SAPInstance",
                              direction=RelationshipDirection.INCOMING,
                              source_alias="host", target_alias="inst") \
            .return_nodes(["host", "inst"]) \
            .build()
        
        assert "(host)<-[r:HOSTED_ON]-(inst:SAPInstance)" in result.query
    
    def test_relationship_traversal_both(self):
        """Traverse bidirectional relationship."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPInstance", alias="inst1") \
            .match_relationship("DEPENDS_ON", "SAPInstance",
                              direction=RelationshipDirection.BOTH,
                              source_alias="inst1", target_alias="inst2") \
            .return_nodes(["inst1", "inst2"]) \
            .build()
        
        assert "(inst1)-[r:DEPENDS_ON]-(inst2:SAPInstance)" in result.query
    
    def test_where_clause(self):
        """Add WHERE clause with parameters."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", alias="sys") \
            .where("sys.landscape_tier = $tier AND sys.active = $active",
                   {"tier": "PRD", "active": True}) \
            .return_nodes() \
            .build()
        
        assert "WHERE sys.landscape_tier = $tier AND sys.active = $active" in result.query
        assert result.parameters["tier"] == "PRD"
        assert result.parameters["active"] == True
    
    def test_return_properties(self):
        """Return specific properties."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", alias="sys") \
            .return_properties("sys", ["sid", "landscape_tier"]) \
            .build()
        
        assert "RETURN sys.sid, sys.landscape_tier" in result.query
    
    def test_order_by_ascending(self):
        """Add ORDER BY clause ascending."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", alias="sys") \
            .return_nodes() \
            .order_by("sys.sid", descending=False) \
            .build()
        
        assert "ORDER BY sys.sid ASC" in result.query
    
    def test_order_by_descending(self):
        """Add ORDER BY clause descending."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", alias="sys") \
            .return_nodes() \
            .order_by("sys.created_at", descending=True) \
            .build()
        
        assert "ORDER BY sys.created_at DESC" in result.query
    
    def test_limit_clause(self):
        """Add LIMIT clause."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem") \
            .return_nodes() \
            .limit(10) \
            .build()
        
        assert "LIMIT 10" in result.query
    
    def test_skip_clause(self):
        """Add SKIP clause for pagination."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem") \
            .return_nodes() \
            .skip(20) \
            .limit(10) \
            .build()
        
        assert "SKIP 20" in result.query
        assert "LIMIT 10" in result.query
    
    def test_complex_query_chaining(self):
        """Build complex query with multiple clauses."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", {"landscape_tier": "PRD"}, alias="sys") \
            .match_relationship("HAS_INSTANCE", "SAPInstance", 
                              source_alias="sys", target_alias="inst") \
            .match_relationship("RUNS_ON", "Host",
                              source_alias="inst", target_alias="host") \
            .where("inst.instance_type = $inst_type", {"inst_type": "PAS"}) \
            .return_nodes(["sys", "inst", "host"]) \
            .order_by("sys.sid") \
            .limit(5) \
            .build()
        
        assert "MATCH (sys:SAPSystem" in result.query
        assert "HAS_INSTANCE" in result.query
        assert "RUNS_ON" in result.query
        assert "WHERE inst.instance_type = $inst_type" in result.query
        assert "RETURN sys, inst, host" in result.query
        assert "ORDER BY sys.sid" in result.query
        assert "LIMIT 5" in result.query
        assert result.parameters["inst_type"] == "PAS"
    
    def test_parameter_uniqueness(self):
        """Each property gets unique parameter name."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", {"sid": "PRD"}, alias="sys1") \
            .match_nodes("SAPSystem", {"sid": "QAS"}, alias="sys2") \
            .return_nodes(["sys1", "sys2"]) \
            .build()
        
        # Should have two different parameter names for "sid"
        assert "sid_1" in result.parameters
        assert "sid_2" in result.parameters
        assert result.parameters["sid_1"] == "PRD"
        assert result.parameters["sid_2"] == "QAS"
    
    def test_complexity_score_simple(self):
        """Simple queries have low complexity."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem") \
            .return_nodes() \
            .build()
        
        assert result.complexity_score < 20
    
    def test_complexity_score_complex(self):
        """Complex queries have higher complexity."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", alias="sys") \
            .match_relationship("HAS_INSTANCE", "SAPInstance", target_alias="inst") \
            .match_relationship("RUNS_ON", "Host", source_alias="inst", target_alias="host") \
            .where("sys.tier = $tier", {"tier": "PRD"}) \
            .return_nodes() \
            .build()
        
        assert result.complexity_score > 30
    
    def test_large_limit_warning(self):
        """Large limits generate warnings."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem") \
            .return_nodes() \
            .limit(2000) \
            .build()
        
        assert len(result.warnings) > 0
        assert "Large limit" in result.warnings[0]
    
    def test_invalid_limit_raises_error(self):
        """Invalid limits raise ValueError."""
        builder = QueryBuilder()
        
        with pytest.raises(ValueError, match="Limit must be at least 1"):
            builder.limit(0)
        
        with pytest.raises(ValueError, match="Limit must be at least 1"):
            builder.limit(-5)
    
    def test_invalid_skip_raises_error(self):
        """Negative skip raises ValueError."""
        builder = QueryBuilder()
        
        with pytest.raises(ValueError, match="Skip must be non-negative"):
            builder.skip(-10)
    
    def test_empty_query_raises_error(self):
        """Building empty query raises ValueError."""
        builder = QueryBuilder()
        
        with pytest.raises(ValueError, match="Cannot build empty query"):
            builder.build()
    
    def test_relationship_with_properties(self):
        """Relationships can have properties."""
        builder = QueryBuilder()
        result = builder \
            .match_nodes("SAPSystem", alias="sys") \
            .match_relationship("TRANSPORTS_TO", "SAPSystem",
                              rel_properties={"route_type": "consolidation"},
                              source_alias="sys", target_alias="target") \
            .return_nodes(["sys", "target"]) \
            .build()
        
        assert "route_type: $rel_route_type_1" in result.query
        assert result.parameters["rel_route_type_1"] == "consolidation"


class TestInjectionPrevention:
    """Test injection attack prevention."""
    
    def test_sql_injection_in_label_blocked(self):
        """SQL injection in label is blocked."""
        builder = QueryBuilder()
        
        with pytest.raises(ValueError):
            builder.match_nodes("SAPSystem; DROP TABLE users; --")
    
    def test_cypher_injection_in_property_blocked(self):
        """Cypher injection in property name is blocked."""
        builder = QueryBuilder()
        
        with pytest.raises(ValueError):
            builder.match_nodes("SAPSystem", {"sid; MATCH (n) DELETE n": "PRD"})
    
    def test_injection_in_relationship_blocked(self):
        """Injection in relationship type is blocked."""
        builder = QueryBuilder()
        builder.match_nodes("SAPSystem", alias="sys")
        
        with pytest.raises(ValueError):
            builder.match_relationship("HAS_INSTANCE; DROP GRAPH;", "SAPInstance")
    
    def test_malicious_param_name_blocked(self):
        """Malicious parameter names are blocked."""
        with pytest.raises(ValueError):
            QueryValidator.validate_param_name("param'; DROP TABLE;")
    
    def test_values_are_parameterized(self):
        """User values never appear in query string."""
        builder = QueryBuilder()
        malicious_value = "'; DROP TABLE users; --"
        
        result = builder \
            .match_nodes("SAPSystem", {"sid": malicious_value}) \
            .return_nodes() \
            .build()
        
        # Malicious value should NOT appear in query string
        assert malicious_value not in result.query
        
        # But should be safely in parameters
        assert malicious_value in result.parameters.values()


class TestSAPQueryTemplates:
    """Test pre-built SAP query templates."""
    
    def test_get_system_by_sid(self):
        """Template: Get system by SID."""
        result = SAPQueryTemplates.get_system_by_sid("PRD")
        
        assert "MATCH (sys:SAPSystem" in result.query
        assert "RETURN sys" in result.query
        assert result.parameters["sid_1"] == "PRD"
    
    def test_get_system_instances(self):
        """Template: Get all instances for system."""
        result = SAPQueryTemplates.get_system_instances("QAS")
        
        assert "SAPSystem" in result.query
        assert "HAS_INSTANCE" in result.query
        assert "SAPInstance" in result.query
        assert result.parameters["sid_1"] == "QAS"
    
    def test_get_production_systems(self):
        """Template: Get all production systems."""
        result = SAPQueryTemplates.get_production_systems()
        
        assert "SAPSystem" in result.query
        assert "WHERE sys.landscape_tier = $tier" in result.query
        assert result.parameters["tier"] == "PRD"
        assert "ORDER BY sys.sid" in result.query
    
    def test_find_instance_dependencies(self):
        """Template: Find instance dependencies."""
        result = SAPQueryTemplates.find_instance_dependencies("PRD_ASCS00")
        
        assert "SAPInstance" in result.query
        assert "DEPENDS_ON" in result.query
        assert result.parameters["name_1"] == "PRD_ASCS00"
    
    def test_get_host_instances(self):
        """Template: Get instances on host."""
        result = SAPQueryTemplates.get_host_instances("server01")
        
        assert "Host" in result.query
        assert "HOSTED_ON" in result.query
        assert "<-" in result.query  # Incoming direction
        assert result.parameters["hostname_1"] == "server01"
    
    def test_find_port_conflicts(self):
        """Template: Find port conflicts."""
        result = SAPQueryTemplates.find_port_conflicts(3200)
        
        assert "SAPInstance" in result.query
        assert "WHERE inst.port = $port" in result.query
        assert result.parameters["port"] == 3200


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_build_safe_query(self):
        """Convenience function builds safe query."""
        query, params = build_safe_query(
            "SAPSystem",
            {"sid": "PRD"},
            return_limit=5
        )
        
        assert "MATCH (n:SAPSystem" in query
        assert "LIMIT 5" in query
        assert "PRD" in params.values()


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("VEDA 4.0 - QUERY BUILDER TEST SUITE")
    print("=" * 70)
    
    # Run all tests
    import sys
    
    # Test 1: Query Validator
    print("\n[TEST 1] Query Validator")
    test_validator = TestQueryValidator()
    try:
        test_validator.test_valid_label_accepted()
        test_validator.test_invalid_label_rejected()
        test_validator.test_valid_relationship_accepted()
        test_validator.test_invalid_relationship_rejected()
        test_validator.test_valid_property_accepted()
        test_validator.test_invalid_property_rejected()
        test_validator.test_valid_param_name_accepted()
        test_validator.test_invalid_param_name_rejected()
        print("✅ Query Validator: 8/8 tests PASSED")
    except Exception as e:
        print(f"❌ Query Validator FAILED: {e}")
        sys.exit(1)
    
    # Test 2: Query Builder
    print("\n[TEST 2] Query Builder")
    test_builder = TestQueryBuilder()
    test_count = 0
    try:
        test_builder.test_simple_match_query()
        test_count += 1
        test_builder.test_match_without_properties()
        test_count += 1
        test_builder.test_custom_alias()
        test_count += 1
        test_builder.test_relationship_traversal_outgoing()
        test_count += 1
        test_builder.test_relationship_traversal_incoming()
        test_count += 1
        test_builder.test_relationship_traversal_both()
        test_count += 1
        test_builder.test_where_clause()
        test_count += 1
        test_builder.test_return_properties()
        test_count += 1
        test_builder.test_order_by_ascending()
        test_count += 1
        test_builder.test_order_by_descending()
        test_count += 1
        test_builder.test_limit_clause()
        test_count += 1
        test_builder.test_skip_clause()
        test_count += 1
        test_builder.test_complex_query_chaining()
        test_count += 1
        test_builder.test_parameter_uniqueness()
        test_count += 1
        test_builder.test_complexity_score_simple()
        test_count += 1
        test_builder.test_complexity_score_complex()
        test_count += 1
        test_builder.test_large_limit_warning()
        test_count += 1
        test_builder.test_invalid_limit_raises_error()
        test_count += 1
        test_builder.test_invalid_skip_raises_error()
        test_count += 1
        test_builder.test_empty_query_raises_error()
        test_count += 1
        test_builder.test_relationship_with_properties()
        test_count += 1
        print(f"✅ Query Builder: {test_count}/21 tests PASSED")
    except Exception as e:
        print(f"❌ Query Builder FAILED at test {test_count + 1}: {e}")
        sys.exit(1)
    
    # Test 3: Injection Prevention
    print("\n[TEST 3] Injection Prevention")
    test_injection = TestInjectionPrevention()
    try:
        test_injection.test_sql_injection_in_label_blocked()
        test_injection.test_cypher_injection_in_property_blocked()
        test_injection.test_injection_in_relationship_blocked()
        test_injection.test_malicious_param_name_blocked()
        test_injection.test_values_are_parameterized()
        print("✅ Injection Prevention: 5/5 tests PASSED")
    except Exception as e:
        print(f"❌ Injection Prevention FAILED: {e}")
        sys.exit(1)
    
    # Test 4: SAP Templates
    print("\n[TEST 4] SAP Query Templates")
    test_templates = TestSAPQueryTemplates()
    try:
        test_templates.test_get_system_by_sid()
        test_templates.test_get_system_instances()
        test_templates.test_get_production_systems()
        test_templates.test_find_instance_dependencies()
        test_templates.test_get_host_instances()
        test_templates.test_find_port_conflicts()
        print("✅ SAP Query Templates: 6/6 tests PASSED")
    except Exception as e:
        print(f"❌ SAP Query Templates FAILED: {e}")
        sys.exit(1)
    
    # Test 5: Convenience Functions
    print("\n[TEST 5] Convenience Functions")
    test_convenience = TestConvenienceFunctions()
    try:
        test_convenience.test_build_safe_query()
        print("✅ Convenience Functions: 1/1 tests PASSED")
    except Exception as e:
        print(f"❌ Convenience Functions FAILED: {e}")
        sys.exit(1)
    
    # Final Summary
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED: 41/41")
    print("=" * 70)
    print("\nQuery Builder Status: READY FOR PRODUCTION")
    print("Layer 3 (Query-level parameterization): COMPLETE")
    print("\nNext Step: Create access_control.py (Layer 4)")
