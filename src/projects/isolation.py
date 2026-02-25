"""
Veda 4.0 - Project Isolation Guards with QueryBuilder (Phase 1 + Phase 2)
Defense-in-depth validation to prevent cross-project data contamination.

ARCHITECTURE (5-Layer Defense):
Layer 1: FalkorDB native multi-graph isolation (physical separation) ✅
Layer 2: Application context enforcement (ProjectContextManager) ✅
Layer 3: Redis key namespacing + Query parameterization (QueryBuilder) ✅ Phase 2
Layer 4: LLM prompt scoping ⏳ (Phase 2)
Layer 5: Response validation (this file) ✅

PURPOSE:
Even though FalkorDB provides physical isolation, this module adds
application-level validation to catch programming errors and detect
any potential cross-contamination before it reaches the user.

PHASE 2 ENHANCEMENTS:
- QueryBuilder integration for injection-safe queries
- Parameterized entity discovery queries
- Graph-based validation helpers

USAGE:
    # Initialize with context manager
    isolation = IsolationGuard(project_manager)

    # Register entities for a project
    isolation.register_entities("client_a", [
        ("SAPSystem", "PRD"),
        ("Host", "server01"),
    ])

    # Auto-discover entities from graph (uses QueryBuilder - Phase 2)
    isolation.auto_register_from_graph("client_a")

    # Validate responses before sending to user
    is_safe = isolation.validate_response(
        response_text="The PRD system is running on server01",
        current_project="client_a"
    )

    # Check for cross-contamination
    violations = isolation.detect_leakage(
        response_text="Client B's QAS system...",
        current_project="client_a"
    )
"""

import re
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

import structlog

# Phase 2: Import QueryBuilder for injection-safe queries
from ..sap.query_builder import QueryBuilder, SAPQueryTemplates

logger = structlog.get_logger()


@dataclass
class EntityReference:
    """Represents a known entity within a project."""
    entity_type: str      # e.g., "SAPSystem", "Host", "IP"
    entity_value: str     # e.g., "PRD", "server01", "10.0.1.50"
    project_id: str       # Which project owns this entity
    registered_at: datetime = field(default_factory=datetime.now)

    def __hash__(self):
        return hash((self.entity_type, self.entity_value, self.project_id))


@dataclass
class ContaminationViolation:
    """Represents a detected cross-project contamination."""
    leaked_entity: EntityReference     # Entity that shouldn't be visible
    found_in_project: str              # Project where it was incorrectly found
    context: str                       # Surrounding text (for debugging)
    severity: str = "HIGH"             # HIGH, MEDIUM, LOW

    def __str__(self):
        return (
            f"[{self.severity}] Entity '{self.leaked_entity.entity_value}' "
            f"from project '{self.leaked_entity.project_id}' "
            f"leaked into '{self.found_in_project}'"
        )


class IsolationGuard:
    """
    Defense-in-depth validation for multi-project isolation.

    GUARANTEES:
    - Detects if a response mentions entities from wrong project
    - Maintains registry of known entities per project
    - Provides audit trail of all validation checks
    - Fails safely (logs warnings, doesn't crash)

    PERFORMANCE:
    - Entity lookup: O(1) via hash set
    - Response scanning: O(n) where n = response length
    - Target overhead: <10ms per validation
    """

    # Sensitive entity types that require strict validation
    SENSITIVE_ENTITY_TYPES = {
        "SAPSystem",      # SAP SID (e.g., PRD, QAS, DEV)
        "Host",           # Server hostnames
        "IPAddress",      # IP addresses
        "Database",       # Database names/SIDs
        "Client",         # SAP client numbers
        "RFCDestination", # RFC connection names
    }

    # Patterns for common entity types (used for auto-detection)
    ENTITY_PATTERNS = {
        "SAPSystem": re.compile(r'\b([A-Z][A-Z0-9]{2})\b'),  # 3-char SID
        "IPAddress": re.compile(
            r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
            r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
        ),
        "Host": re.compile(r'\b([a-z0-9\-]+\.[a-z0-9\-\.]+)\b', re.IGNORECASE),
    }

    def __init__(self, project_manager=None):
        """
        Initialize isolation guard.

        Args:
            project_manager: Optional ProjectContextManager instance
                            (for auto-detection features)
        """
        self.project_manager = project_manager

        # Entity registry: {project_id: {EntityReference, ...}}
        self._registry: Dict[str, Set[EntityReference]] = defaultdict(set)

        # Reverse lookup: {(type, value): project_id}
        # For fast "which project owns this entity?" queries
        self._reverse_lookup: Dict[Tuple[str, str], str] = {}

        # Audit log: All validation checks
        self._audit_log: List[Dict] = []

        # Statistics
        self._stats = {
            "validations_performed": 0,
            "violations_detected": 0,
            "entities_registered": 0,
        }

        logger.info("isolation_guard_initialized", querybuilder_enabled=True)

    def register_entity(
        self,
        project_id: str,
        entity_type: str,
        entity_value: str
    ):
        """
        Register a known entity for a project.

        This builds the "entity ownership map" used for cross-contamination
        detection. When you create a SAP system in Client A, register it here.

        Args:
            project_id: Project that owns this entity
            entity_type: Type of entity (e.g., "SAPSystem", "Host")
            entity_value: Actual value (e.g., "PRD", "server01")

        Example:
            guard.register_entity("client_a", "SAPSystem", "PRD")
            guard.register_entity("client_a", "Host", "prd-app01")
        """
        entity = EntityReference(
            entity_type=entity_type,
            entity_value=entity_value,
            project_id=project_id
        )

        # Add to project's entity set
        self._registry[project_id].add(entity)

        # Add to reverse lookup
        self._reverse_lookup[(entity_type, entity_value)] = project_id

        self._stats["entities_registered"] += 1

        logger.debug(
            "entity_registered",
            project_id=project_id,
            entity_type=entity_type,
            entity_value=entity_value
        )

    def register_entities(
        self,
        project_id: str,
        entities: List[Tuple[str, str]]
    ):
        """
        Register multiple entities at once.

        Args:
            project_id: Project that owns these entities
            entities: List of (type, value) tuples

        Example:
            guard.register_entities("client_a", [
                ("SAPSystem", "PRD"),
                ("SAPSystem", "QAS"),
                ("Host", "prd-app01"),
                ("IPAddress", "10.0.1.50"),
            ])
        """
        for entity_type, entity_value in entities:
            self.register_entity(project_id, entity_type, entity_value)

        logger.info(
            "bulk_entities_registered",
            project_id=project_id,
            count=len(entities)
        )

    def get_entity_owner(
        self,
        entity_type: str,
        entity_value: str
    ) -> Optional[str]:
        """
        Look up which project owns an entity.

        Args:
            entity_type: Type of entity
            entity_value: Entity value

        Returns:
            Project ID that owns this entity, or None if not registered

        Example:
            >>> guard.get_entity_owner("SAPSystem", "PRD")
            'client_a'
        """
        return self._reverse_lookup.get((entity_type, entity_value))

    def detect_leakage(
        self,
        text: str,
        current_project: str,
        context_window: int = 50
    ) -> List[ContaminationViolation]:
        """
        Scan text for entities that belong to OTHER projects.

        This is the core cross-contamination detection algorithm.
        It searches for registered entities and checks if they belong
        to a different project than the current one.

        Args:
            text: Text to scan (e.g., LLM response)
            current_project: Currently active project ID
            context_window: Characters of context to capture around violation

        Returns:
            List of detected violations (empty if clean)

        Example:
            >>> violations = guard.detect_leakage(
            ...     "Client B's QAS system is down",
            ...     current_project="client_a"
            ... )
            >>> if violations:
            ...     print(f"CONTAMINATION DETECTED: {violations[0]}")
        """
        violations = []

        # Scan for all registered entities
        for (entity_type, entity_value), owner_project in self._reverse_lookup.items():
            # Skip entities that belong to current project (they're allowed)
            if owner_project == current_project:
                continue

            # Search for this entity in the text
            # Use word boundaries to avoid false positives
            pattern = re.compile(rf'\b{re.escape(entity_value)}\b', re.IGNORECASE)

            for match in pattern.finditer(text):
                # Found an entity from a DIFFERENT project - this is a leak!
                start = max(0, match.start() - context_window)
                end = min(len(text), match.end() + context_window)
                context = text[start:end]

                leaked_entity = EntityReference(
                    entity_type=entity_type,
                    entity_value=entity_value,
                    project_id=owner_project
                )

                violation = ContaminationViolation(
                    leaked_entity=leaked_entity,
                    found_in_project=current_project,
                    context=context,
                    severity="HIGH" if entity_type in self.SENSITIVE_ENTITY_TYPES else "MEDIUM"
                )

                violations.append(violation)

                logger.warning(
                    "cross_contamination_detected",
                    entity_type=entity_type,
                    entity_value=entity_value,
                    owner_project=owner_project,
                    found_in_project=current_project,
                    context=context[:100]
                )

        self._stats["violations_detected"] += len(violations)

        return violations

    def validate_response(
        self,
        response_text: str,
        current_project: str,
        raise_on_violation: bool = False
    ) -> bool:
        """
        Validate that a response contains no cross-project contamination.

        This is the main method you call before sending responses to users.

        Args:
            response_text: Response to validate
            current_project: Currently active project
            raise_on_violation: If True, raise exception on contamination

        Returns:
            True if clean, False if contaminated

        Raises:
            RuntimeError: If contamination detected and raise_on_violation=True

        Example:
            >>> response = generate_response()
            >>> if not guard.validate_response(response, "client_a"):
            ...     # Handle contamination - don't send to user!
            ...     response = "Error: Internal data validation failed"
        """
        self._stats["validations_performed"] += 1

        violations = self.detect_leakage(response_text, current_project)

        # Log to audit trail
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "project": current_project,
            "response_length": len(response_text),
            "violations_found": len(violations),
            "is_clean": len(violations) == 0,
        }
        self._audit_log.append(audit_entry)

        if violations:
            logger.error(
                "response_validation_failed",
                project=current_project,
                violations=len(violations),
                severity=max(v.severity for v in violations)
            )

            if raise_on_violation:
                violation_summary = "\n".join(str(v) for v in violations[:3])
                raise RuntimeError(
                    f"Cross-project contamination detected:\n{violation_summary}"
                )

            return False

        logger.debug(
            "response_validation_passed",
            project=current_project,
            response_length=len(response_text)
        )

        return True

    def get_project_entities(self, project_id: str) -> Set[EntityReference]:
        """
        Get all registered entities for a project.

        Args:
            project_id: Project to query

        Returns:
            Set of EntityReference objects

        Example:
            >>> entities = guard.get_project_entities("client_a")
            >>> print(f"Client A has {len(entities)} registered entities")
        """
        return self._registry.get(project_id, set())

    def clear_project_entities(self, project_id: str):
        """
        Clear all registered entities for a project.

        Use when deleting a project or for testing.

        Args:
            project_id: Project to clear
        """
        entities = self._registry.get(project_id, set())

        # Remove from reverse lookup
        for entity in entities:
            key = (entity.entity_type, entity.entity_value)
            if key in self._reverse_lookup:
                del self._reverse_lookup[key]

        # Clear from registry
        if project_id in self._registry:
            del self._registry[project_id]

        logger.info(
            "project_entities_cleared",
            project_id=project_id,
            entities_removed=len(entities)
        )

    def get_statistics(self) -> Dict:
        """
        Get isolation guard statistics.

        Returns:
            Dict with validation metrics

        Example:
            >>> stats = guard.get_statistics()
            >>> print(f"Validations: {stats['validations_performed']}")
            >>> print(f"Violations: {stats['violations_detected']}")
        """
        return {
            **self._stats,
            "registered_projects": len(self._registry),
            "total_entities": sum(len(entities) for entities in self._registry.values()),
            "audit_log_size": len(self._audit_log),
        }

    def get_audit_log(
        self,
        project_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Retrieve audit log entries.

        Args:
            project_id: Optional filter by project
            limit: Maximum entries to return

        Returns:
            List of audit log entries (most recent first)
        """
        logs = self._audit_log

        if project_id:
            logs = [log for log in logs if log.get("project") == project_id]

        return list(reversed(logs))[-limit:]

    def auto_register_from_graph(self, project_id: str):
        """
        Auto-discover and register entities from a project's graph.

        Scans the mounted project's graph and registers all entities
        with recognizable types (SAPSystem, Host, etc.).

        PHASE 2: Now uses QueryBuilder for injection-safe queries.

        Args:
            project_id: Project to scan

        Raises:
            RuntimeError: If project_manager not provided or project not mounted

        Example:
            >>> guard.auto_register_from_graph("client_a")
            >>> entities = guard.get_project_entities("client_a")
            >>> print(f"Auto-registered {len(entities)} entities")
        """
        if not self.project_manager:
            raise RuntimeError(
                "auto_register_from_graph requires project_manager "
                "to be provided during initialization"
            )

        # Mount the project
        self.project_manager.mount(project_id)

        registered_count = 0

        # Phase 2: Use QueryBuilder for safe, parameterized queries
        # Query 1: Find all SAP Systems
        builder = QueryBuilder()
        sap_systems_query = builder.match_nodes("SAPSystem").return_properties("n", ["sid"]).build()
        
        result = self.project_manager.query(sap_systems_query.query, sap_systems_query.parameters)
        for row in result.result_set:
            if row[0]:  # sid exists
                self.register_entity(project_id, "SAPSystem", row[0])
                registered_count += 1
        
        logger.debug(
            "sap_systems_registered",
            project_id=project_id,
            count=len(result.result_set) if result.result_set else 0
        )

        # Query 2: Find all Hosts with hostnames and IPs
        builder = QueryBuilder()
        hosts_query = builder.match_nodes("Host").return_properties("n", ["hostname", "ip"]).build()
        
        result = self.project_manager.query(hosts_query.query, hosts_query.parameters)
        for row in result.result_set:
            hostname = row[0] if len(row) > 0 else None
            ip = row[1] if len(row) > 1 else None
            
            if hostname:
                self.register_entity(project_id, "Host", hostname)
                registered_count += 1
            if ip:
                self.register_entity(project_id, "IPAddress", ip)
                registered_count += 1
        
        logger.debug(
            "hosts_registered",
            project_id=project_id,
            count=len(result.result_set) if result.result_set else 0
        )

        # Query 3: Find all Databases
        builder = QueryBuilder()
        databases_query = builder.match_nodes("Database").return_properties("n", ["db_sid"]).build()
        
        result = self.project_manager.query(databases_query.query, databases_query.parameters)
        for row in result.result_set:
            if row[0]:  # db_sid exists
                self.register_entity(project_id, "Database", row[0])
                registered_count += 1
        
        logger.debug(
            "databases_registered",
            project_id=project_id,
            count=len(result.result_set) if result.result_set else 0
        )

        logger.info(
            "auto_registration_complete",
            project_id=project_id,
            entities_registered=registered_count,
            method="querybuilder"
        )

        return registered_count

    def validate_with_graph(
        self,
        project_id: str
    ) -> Dict[str, int]:
        """
        Validate registered entities against actual graph data.
        
        Uses QueryBuilder to construct safe queries for cross-verification.
        Checks if registered entities still exist in the graph.
        
        PHASE 2: New helper method for graph-based validation.
        
        Args:
            project_id: Project to validate
        
        Returns:
            Dict with validation statistics
        
        Example:
            >>> stats = guard.validate_with_graph("client_a")
            >>> print(f"Verified: {stats['entities_verified']}")
            >>> print(f"Missing: {stats['entities_missing']}")
        """
        if not self.project_manager:
            raise RuntimeError(
                "validate_with_graph requires project_manager "
                "to be provided during initialization"
            )
        
        logger.info(
            "graph_validation_started",
            project_id=project_id
        )
        
        # Mount the project
        self.project_manager.mount(project_id)
        
        # Get registered entities
        registered_entities = self.get_project_entities(project_id)
        
        verified = 0
        missing = 0
        
        # Verify each entity type using QueryBuilder
        for entity in registered_entities:
            builder = QueryBuilder()
            
            # Build query based on entity type
            if entity.entity_type == "SAPSystem":
                query_result = builder \
                    .match_nodes("SAPSystem", {"sid": entity.entity_value}) \
                    .return_nodes() \
                    .build()
            elif entity.entity_type == "Host":
                query_result = builder \
                    .match_nodes("Host", {"hostname": entity.entity_value}) \
                    .return_nodes() \
                    .build()
            elif entity.entity_type == "Database":
                query_result = builder \
                    .match_nodes("Database", {"db_sid": entity.entity_value}) \
                    .return_nodes() \
                    .build()
            else:
                # Skip unknown entity types
                continue
            
            # Execute query
            result = self.project_manager.query(
                query_result.query,
                query_result.parameters
            )
            
            if result.result_set and len(result.result_set) > 0:
                verified += 1
            else:
                missing += 1
                logger.warning(
                    "entity_not_in_graph",
                    project_id=project_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.entity_value
                )
        
        stats = {
            "project_id": project_id,
            "entities_registered": len(registered_entities),
            "entities_verified": verified,
            "entities_missing": missing,
            "verification_complete": True
        }
        
        logger.info(
            "graph_validation_complete",
            **stats
        )
        
        return stats


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def sanitize_response(
    response: str,
    violations: List[ContaminationViolation],
    replacement: str = "[REDACTED]"
) -> str:
    """
    Sanitize a contaminated response by replacing leaked entities.

    Use this as a fallback when contamination is detected but you still
    need to return something to the user.

    Args:
        response: Original response with contamination
        violations: List of detected violations
        replacement: Text to replace leaked entities with

    Returns:
        Sanitized response

    Example:
        >>> response = "Client B's QAS system is at 10.2.3.4"
        >>> violations = guard.detect_leakage(response, "client_a")
        >>> clean = sanitize_response(response, violations)
        >>> print(clean)
        "[REDACTED]'s [REDACTED] system is at [REDACTED]"
    """
    sanitized = response

    for violation in violations:
        entity_value = violation.leaked_entity.entity_value
        # Replace with word boundaries to avoid partial replacements
        pattern = re.compile(rf'\b{re.escape(entity_value)}\b', re.IGNORECASE)
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def create_isolation_report(guard: IsolationGuard) -> str:
    """
    Generate a human-readable isolation status report.

    Args:
        guard: IsolationGuard instance

    Returns:
        Formatted report string
    """
    stats = guard.get_statistics()

    report = []
    report.append("=" * 60)
    report.append("ISOLATION GUARD STATUS REPORT")
    report.append("=" * 60)
    report.append(f"Registered Projects: {stats['registered_projects']}")
    report.append(f"Total Entities: {stats['total_entities']}")
    report.append(f"Validations Performed: {stats['validations_performed']}")
    report.append(f"Violations Detected: {stats['violations_detected']}")

    if stats['validations_performed'] > 0:
        contamination_rate = (
            stats['violations_detected'] / stats['validations_performed'] * 100
        )
        report.append(f"Contamination Rate: {contamination_rate:.2f}%")

    report.append("=" * 60)

    return "\n".join(report)


# End of IsolationGuard implementation with QueryBuilder integration
