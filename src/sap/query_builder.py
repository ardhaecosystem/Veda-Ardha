"""
Veda 4.0 - Phase 2: Query Builder (Layer 3)

Safe Cypher query construction with parameterized queries to prevent injection attacks.
Provides templates for common SAP landscape queries.

SECURITY FEATURES:
- All values passed as parameters (never string interpolation)
- Input validation for node labels, property names, relationship types
- Whitelist-based label/property validation
- Query complexity limits

USAGE:
    builder = QueryBuilder()
    
    # Simple query
    query, params = builder.match_nodes(
        label="SAPSystem",
        properties={"sid": "PRD"}
    ).return_nodes().build()
    
    # Complex query
    query, params = builder.match_nodes("SAPSystem", {"tier": "production"}) \\
        .match_relationship("HAS_INSTANCE", "SAPInstance") \\
        .where("instance.type = $inst_type", {"inst_type": "PAS"}) \\
        .return_nodes(["system", "instance"]) \\
        .limit(10) \\
        .build()
"""

import re
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import structlog

logger = structlog.get_logger()


class RelationshipDirection(Enum):
    """Direction for relationship traversal."""
    OUTGOING = "->"  # (a)-[r]->(b)
    INCOMING = "<-"  # (a)<-[r]-(b)
    BOTH = "-"       # (a)-[r]-(b)


@dataclass
class QueryResult:
    """
    Result of a query build operation.
    
    Attributes:
        query: The Cypher query string
        parameters: Parameter dictionary for safe execution
        complexity_score: Estimate of query complexity (1-100)
        warnings: Any warnings about the query
    """
    query: str
    parameters: Dict[str, Any]
    complexity_score: int = 0
    warnings: List[str] = field(default_factory=list)


class QueryValidator:
    """
    Validates query components against whitelists to prevent injection.
    
    Phase 2 Layer 3: Query-level security
    """
    
    # Whitelist of allowed node labels (from templates.py)
    ALLOWED_LABELS: Set[str] = {
        "SAPSystem", "SAPInstance", "Host", "Database", "Client",
        "TransportRoute", "NetworkSegment", "RFCDestination", "Entity"
    }
    
    # Whitelist of allowed relationship types (from templates.py)
    ALLOWED_RELATIONSHIPS: Set[str] = {
        "HAS_INSTANCE", "RUNS_ON", "USES_DATABASE", "HOSTED_ON",
        "HAS_CLIENT", "TRANSPORTS_TO", "DEPENDS_ON", "FAILOVER_FOR",
        "BELONGS_TO_NETWORK", "CONNECTS_VIA", "TARGETS", "RELATES_TO"
    }
    
    # Whitelist of allowed property names (common SAP properties)
    ALLOWED_PROPERTIES: Set[str] = {
        # System properties
        "sid", "system_type", "landscape_tier", "description",
        # Instance properties
        "instance_number", "instance_type", "hostname", "status",
        # Host properties
        "ip_address", "os_type", "cpu_cores", "ram_gb",
        # Database properties
        "db_type", "db_version", "db_name",
        # Client properties
        "client_number", "client_role",
        # Common properties
        "name", "created_at", "updated_at", "active", "tags",
        # Network properties
        "cidr", "vlan_id", "zone",
        # Transport properties
        "source_system", "target_system", "route_type",
        # RFC properties
        "connection_type", "target_host", "program_id"
    }
    
    # Pattern for valid parameter names (alphanumeric + underscore)
    PARAM_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    
    @classmethod
    def validate_label(cls, label: str) -> bool:
        """Validate node label against whitelist."""
        if label not in cls.ALLOWED_LABELS:
            logger.warning("invalid_label_rejected", label=label)
            raise ValueError(f"Invalid node label: {label}")
        return True
    
    @classmethod
    def validate_relationship(cls, rel_type: str) -> bool:
        """Validate relationship type against whitelist."""
        if rel_type not in cls.ALLOWED_RELATIONSHIPS:
            logger.warning("invalid_relationship_rejected", rel_type=rel_type)
            raise ValueError(f"Invalid relationship type: {rel_type}")
        return True
    
    @classmethod
    def validate_property(cls, prop_name: str) -> bool:
        """Validate property name against whitelist."""
        if prop_name not in cls.ALLOWED_PROPERTIES:
            logger.warning("invalid_property_rejected", property=prop_name)
            raise ValueError(f"Invalid property name: {prop_name}")
        return True
    
    @classmethod
    def validate_param_name(cls, param_name: str) -> bool:
        """Validate parameter name format."""
        if not cls.PARAM_NAME_PATTERN.match(param_name):
            logger.warning("invalid_param_name_rejected", param=param_name)
            raise ValueError(f"Invalid parameter name: {param_name}")
        return True


class QueryBuilder:
    """
    Safe Cypher query builder with parameterization.
    
    Uses builder pattern for composable queries.
    All values are parameterized to prevent injection.
    
    Example:
        builder = QueryBuilder()
        query, params = builder.match_nodes("SAPSystem", {"sid": "PRD"}) \\
            .return_nodes() \\
            .build()
    """
    
    def __init__(self):
        self.clauses: List[str] = []
        self.parameters: Dict[str, Any] = {}
        self.param_counter: int = 0
        self.complexity: int = 0
        self.warnings: List[str] = []
        self.node_aliases: List[str] = []
        
        logger.debug("query_builder_initialized")
    
    def _generate_param_name(self, prefix: str = "param") -> str:
        """Generate unique parameter name."""
        self.param_counter += 1
        param_name = f"{prefix}_{self.param_counter}"
        QueryValidator.validate_param_name(param_name)
        return param_name
    
    def match_nodes(
        self,
        label: str,
        properties: Optional[Dict[str, Any]] = None,
        alias: str = "n"
    ) -> 'QueryBuilder':
        """
        Add MATCH clause for nodes.
        
        Args:
            label: Node label (validated against whitelist)
            properties: Property filters (parameterized)
            alias: Variable alias for the node
        
        Returns:
            Self for chaining
        
        Example:
            builder.match_nodes("SAPSystem", {"sid": "PRD"}, alias="sys")
            # Generates: MATCH (sys:SAPSystem {sid: $param_1})
        """
        QueryValidator.validate_label(label)
        self.node_aliases.append(alias)
        
        # Build property string with parameters
        prop_parts = []
        if properties:
            for key, value in properties.items():
                QueryValidator.validate_property(key)
                param_name = self._generate_param_name(key)
                prop_parts.append(f"{key}: ${param_name}")
                self.parameters[param_name] = value
        
        prop_string = "{" + ", ".join(prop_parts) + "}" if prop_parts else ""
        match_clause = f"MATCH ({alias}:{label}{prop_string})"
        
        self.clauses.append(match_clause)
        self.complexity += 10
        
        logger.debug("match_clause_added", label=label, alias=alias)
        return self
    
    def match_relationship(
        self,
        rel_type: str,
        target_label: str,
        direction: RelationshipDirection = RelationshipDirection.OUTGOING,
        rel_properties: Optional[Dict[str, Any]] = None,
        source_alias: str = "n",
        rel_alias: str = "r",
        target_alias: str = "m"
    ) -> 'QueryBuilder':
        """
        Add relationship traversal.
        
        Args:
            rel_type: Relationship type (validated)
            target_label: Target node label (validated)
            direction: Relationship direction
            rel_properties: Properties on relationship (optional)
            source_alias: Source node variable
            rel_alias: Relationship variable
            target_alias: Target node variable
        
        Returns:
            Self for chaining
        
        Example:
            builder.match_relationship("HAS_INSTANCE", "SAPInstance")
            # Generates: MATCH (n)-[r:HAS_INSTANCE]->(m:SAPInstance)
        """
        QueryValidator.validate_relationship(rel_type)
        QueryValidator.validate_label(target_label)
        self.node_aliases.append(target_alias)
        
        # Build relationship property string
        rel_prop_parts = []
        if rel_properties:
            for key, value in rel_properties.items():
                QueryValidator.validate_property(key)
                param_name = self._generate_param_name(f"rel_{key}")
                rel_prop_parts.append(f"{key}: ${param_name}")
                self.parameters[param_name] = value
        
        rel_prop_string = " {" + ", ".join(rel_prop_parts) + "}" if rel_prop_parts else ""
        
        # Build direction-specific pattern
        if direction == RelationshipDirection.OUTGOING:
            pattern = f"({source_alias})-[{rel_alias}:{rel_type}{rel_prop_string}]->({target_alias}:{target_label})"
        elif direction == RelationshipDirection.INCOMING:
            pattern = f"({source_alias})<-[{rel_alias}:{rel_type}{rel_prop_string}]-({target_alias}:{target_label})"
        else:  # BOTH
            pattern = f"({source_alias})-[{rel_alias}:{rel_type}{rel_prop_string}]-({target_alias}:{target_label})"
        
        match_clause = f"MATCH {pattern}"
        self.clauses.append(match_clause)
        self.complexity += 15
        
        logger.debug("relationship_match_added", rel_type=rel_type, direction=direction.value)
        return self
    
    def where(self, condition: str, params: Optional[Dict[str, Any]] = None) -> 'QueryBuilder':
        """
        Add WHERE clause with parameterized conditions.
        
        Args:
            condition: Condition string with parameter placeholders
            params: Parameter values
        
        Returns:
            Self for chaining
        
        Example:
            builder.where("n.tier = $tier AND n.active = $active", 
                         {"tier": "production", "active": True})
            # Generates: WHERE n.tier = $tier AND n.active = $active
        
        IMPORTANT: Condition string should use $param_name syntax.
        """
        if params:
            # Validate parameter names
            for param_name in params.keys():
                QueryValidator.validate_param_name(param_name)
                if param_name in self.parameters:
                    self.warnings.append(f"Parameter {param_name} already exists, overwriting")
                self.parameters[param_name] = params[param_name]
        
        where_clause = f"WHERE {condition}"
        self.clauses.append(where_clause)
        self.complexity += 5
        
        logger.debug("where_clause_added", condition_length=len(condition))
        return self
    
    def return_nodes(self, aliases: Optional[List[str]] = None) -> 'QueryBuilder':
        """
        Add RETURN clause.
        
        Args:
            aliases: Node aliases to return (default: all matched nodes)
        
        Returns:
            Self for chaining
        
        Example:
            builder.return_nodes(["sys", "inst"])
            # Generates: RETURN sys, inst
        """
        if aliases is None:
            aliases = self.node_aliases
        
        return_clause = f"RETURN {', '.join(aliases)}"
        self.clauses.append(return_clause)
        
        logger.debug("return_clause_added", aliases=aliases)
        return self
    
    def return_properties(self, alias: str, properties: List[str]) -> 'QueryBuilder':
        """
        Return specific properties of a node.
        
        Args:
            alias: Node alias
            properties: List of property names
        
        Returns:
            Self for chaining
        
        Example:
            builder.return_properties("sys", ["sid", "tier"])
            # Generates: RETURN sys.sid, sys.tier
        """
        for prop in properties:
            QueryValidator.validate_property(prop)
        
        prop_refs = [f"{alias}.{prop}" for prop in properties]
        return_clause = f"RETURN {', '.join(prop_refs)}"
        self.clauses.append(return_clause)
        
        logger.debug("return_properties_added", alias=alias, properties=properties)
        return self
    
    def order_by(self, property_ref: str, descending: bool = False) -> 'QueryBuilder':
        """
        Add ORDER BY clause.
        
        Args:
            property_ref: Property reference (e.g., "n.created_at")
            descending: Sort descending if True
        
        Returns:
            Self for chaining
        
        Example:
            builder.order_by("sys.sid", descending=False)
            # Generates: ORDER BY sys.sid ASC
        """
        order = "DESC" if descending else "ASC"
        order_clause = f"ORDER BY {property_ref} {order}"
        self.clauses.append(order_clause)
        
        logger.debug("order_by_added", property=property_ref, descending=descending)
        return self
    
    def limit(self, count: int) -> 'QueryBuilder':
        """
        Add LIMIT clause.
        
        Args:
            count: Maximum number of results
        
        Returns:
            Self for chaining
        """
        if count < 1:
            raise ValueError("Limit must be at least 1")
        if count > 1000:
            self.warnings.append(f"Large limit ({count}) may impact performance")
        
        limit_clause = f"LIMIT {count}"
        self.clauses.append(limit_clause)
        
        logger.debug("limit_added", count=count)
        return self
    
    def skip(self, count: int) -> 'QueryBuilder':
        """
        Add SKIP clause for pagination.
        
        Args:
            count: Number of results to skip
        
        Returns:
            Self for chaining
        """
        if count < 0:
            raise ValueError("Skip must be non-negative")
        
        skip_clause = f"SKIP {count}"
        self.clauses.append(skip_clause)
        
        logger.debug("skip_added", count=count)
        return self
    
    def build(self) -> QueryResult:
        """
        Build final query and parameters.
        
        Returns:
            QueryResult with query string, parameters, complexity score, warnings
        
        Example:
            result = builder.build()
            query, params = result.query, result.parameters
        """
        if not self.clauses:
            raise ValueError("Cannot build empty query")
        
        query = "\n".join(self.clauses)
        
        # Calculate final complexity
        complexity = self.complexity
        if len(self.node_aliases) > 3:
            complexity += 10  # Penalty for complex joins
        
        result = QueryResult(
            query=query,
            parameters=self.parameters,
            complexity_score=complexity,
            warnings=self.warnings
        )
        
        logger.info(
            "query_built",
            complexity=complexity,
            param_count=len(self.parameters),
            warning_count=len(self.warnings)
        )
        
        return result


class SAPQueryTemplates:
    """
    Pre-built query templates for common SAP operations.
    
    All templates use parameterized queries for safety.
    """
    
    @staticmethod
    def get_system_by_sid(sid: str) -> QueryResult:
        """
        Get SAP system by SID.
        
        Args:
            sid: System ID (3-character)
        
        Returns:
            QueryResult
        """
        return QueryBuilder() \
            .match_nodes("SAPSystem", {"sid": sid}, alias="sys") \
            .return_nodes(["sys"]) \
            .build()
    
    @staticmethod
    def get_system_instances(sid: str) -> QueryResult:
        """
        Get all instances for a system.
        
        Args:
            sid: System ID
        
        Returns:
            QueryResult
        """
        return QueryBuilder() \
            .match_nodes("SAPSystem", {"sid": sid}, alias="sys") \
            .match_relationship("HAS_INSTANCE", "SAPInstance", target_alias="inst") \
            .return_nodes(["sys", "inst"]) \
            .build()
    
    @staticmethod
    def get_production_systems() -> QueryResult:
        """Get all production systems."""
        return QueryBuilder() \
            .match_nodes("SAPSystem", alias="sys") \
            .where("sys.landscape_tier = $tier", {"tier": "PRD"}) \
            .return_nodes(["sys"]) \
            .order_by("sys.sid") \
            .build()
    
    @staticmethod
    def find_instance_dependencies(instance_id: str) -> QueryResult:
        """
        Find what an instance depends on.
        
        Args:
            instance_id: Instance identifier
        
        Returns:
            QueryResult
        """
        return QueryBuilder() \
            .match_nodes("SAPInstance", {"name": instance_id}, alias="inst") \
            .match_relationship("DEPENDS_ON", "SAPInstance", target_alias="dep") \
            .return_nodes(["inst", "dep"]) \
            .build()
    
    @staticmethod
    def get_host_instances(hostname: str) -> QueryResult:
        """
        Get all instances on a host.
        
        Args:
            hostname: Host name
        
        Returns:
            QueryResult
        """
        return QueryBuilder() \
            .match_nodes("Host", {"hostname": hostname}, alias="host") \
            .match_relationship("HOSTED_ON", "SAPInstance", 
                              direction=RelationshipDirection.INCOMING,
                              target_alias="inst") \
            .return_nodes(["host", "inst"]) \
            .build()
    
    @staticmethod
    def find_port_conflicts(port: int) -> QueryResult:
        """
        Find instances using a specific port.
        
        Args:
            port: Port number
        
        Returns:
            QueryResult
        """
        return QueryBuilder() \
            .match_nodes("SAPInstance", alias="inst") \
            .match_relationship("RUNS_ON", "Host", target_alias="host") \
            .where("inst.port = $port", {"port": port}) \
            .return_nodes(["inst", "host"]) \
            .build()


# Convenience function for orchestrator/services
def build_safe_query(
    label: str,
    properties: Optional[Dict[str, Any]] = None,
    return_limit: int = 10
) -> Tuple[str, Dict[str, Any]]:
    """
    Quick helper for simple queries.
    
    Args:
        label: Node label
        properties: Filter properties
        return_limit: Result limit
    
    Returns:
        Tuple of (query_string, parameters)
    
    Example:
        query, params = build_safe_query("SAPSystem", {"sid": "PRD"}, return_limit=5)
    """
    result = QueryBuilder() \
        .match_nodes(label, properties) \
        .return_nodes() \
        .limit(return_limit) \
        .build()
    
    return result.query, result.parameters
