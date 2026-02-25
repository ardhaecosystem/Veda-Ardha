"""
Veda 4.0 - Phase 2 Week 2: SAP Knowledge Service

Unified API for SAP landscape operations.
Wraps Phase 1 modules (ontology, port_calculator, dependency_rules, validators)
with QueryBuilder integration for safe queries.

PURPOSE:
- Single entry point for all SAP operations
- High-level API (no raw Cypher queries)
- Project-aware (uses ProjectContextManager)
- Type-safe (returns Pydantic models)
- Injection-proof (uses QueryBuilder)

MODULES INTEGRATED:
- ontology.py: SAPSystem, SAPInstance, Host models
- port_calculator.py: Port calculation functions
- dependency_rules.py: Startup order and dependencies
- validators.py: Cross-entity validation
- query_builder.py: Safe parameterized queries

USAGE:
    from src.sap.knowledge_service import SAPKnowledgeService
    
    # Initialize with project context
    service = SAPKnowledgeService(
        project_manager=manager,
        project_id="client_acme"
    )
    
    # Get system by SID
    system = service.get_system_by_sid("PRD")
    
    # Calculate ports for instance
    ports = service.calculate_instance_ports("00", "PAS")
    
    # Get startup sequence
    sequence = service.get_startup_sequence()
    
    # Find port conflicts
    conflicts = service.find_port_conflicts()
    
    # Validate landscape
    validation = service.validate_landscape()
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

import structlog

# Import Phase 1 modules
from .ontology import SAPSystem, SAPInstance, Host
from .port_calculator import (
    calculate_instance_ports,
    calculate_dispatcher_port,
    calculate_gateway_port,
    calculate_message_server_port,
    calculate_http_port,
    calculate_https_port,
    calculate_hana_sql_port,
    calculate_hana_systemdb_port,
    calculate_hana_indexserver_port
)
from .dependency_rules import (
    DependencyValidator,
    StartupSequence,
    StartupPriority,
    DependencyRule
)
from .validators import (
    ValidationResult,
    validate_sid_uniqueness,
    validate_sid_format_batch
)

# Import Phase 2 QueryBuilder
from .query_builder import QueryBuilder, SAPQueryTemplates

logger = structlog.get_logger()


@dataclass
class PortConflict:
    """Represents a port conflict between two instances."""
    port: int
    instance1: Dict
    instance2: Dict
    severity: str = "HIGH"  # HIGH, MEDIUM, LOW
    
    def __str__(self) -> str:
        return (
            f"[{self.severity}] Port {self.port} conflict: "
            f"{self.instance1.get('sid')}/{self.instance1.get('instance_number')} vs "
            f"{self.instance2.get('sid')}/{self.instance2.get('instance_number')}"
        )


@dataclass
class LandscapeHealth:
    """Overall landscape health status."""
    total_systems: int
    total_instances: int
    active_systems: int
    port_conflicts: List[PortConflict]
    missing_dependencies: List[DependencyRule]
    validation_errors: List[str]
    validation_warnings: List[str]
    health_score: float  # 0.0 to 1.0
    
    @property
    def is_healthy(self) -> bool:
        """Check if landscape is healthy (score >= 0.8)."""
        return self.health_score >= 0.8
    
    def __str__(self) -> str:
        status = "✅ HEALTHY" if self.is_healthy else "⚠️ ISSUES DETECTED"
        return (
            f"{status} | Score: {self.health_score:.2f} | "
            f"Systems: {self.active_systems}/{self.total_systems} | "
            f"Conflicts: {len(self.port_conflicts)} | "
            f"Errors: {len(self.validation_errors)}"
        )


class SAPKnowledgeService:
    """
    Unified API for SAP landscape operations.
    
    Combines all Phase 1 SAP modules with QueryBuilder for safe queries.
    Provides high-level operations without requiring Cypher knowledge.
    """
    
    def __init__(
        self,
        project_manager,  # ProjectContextManager instance
        project_id: Optional[str] = None
    ):
        """
        Initialize SAP Knowledge Service.
        
        Args:
            project_manager: ProjectContextManager instance
            project_id: Optional project to mount (if None, assumes already mounted)
        """
        self.project_manager = project_manager
        self.project_id = project_id
        
        # Mount project if specified
        if project_id:
            self.project_manager.mount(project_id)
            logger.info(
                "knowledge_service_initialized",
                project_id=project_id
            )
        else:
            # Use currently mounted project
            try:
                current = self.project_manager.current
                self.project_id = current.project_id
                logger.info(
                    "knowledge_service_initialized",
                    project_id=self.project_id
                )
            except RuntimeError:
                logger.warning("knowledge_service_no_project_mounted")
                self.project_id = None
        
        # Initialize dependency validator
        self.dependency_validator = DependencyValidator()
    
    # =========================================================================
    # SYSTEM QUERIES (Uses QueryBuilder)
    # =========================================================================
    
    def get_system_by_sid(self, sid: str) -> Optional[Dict]:
        """
        Get system by SID.
        
        Args:
            sid: System ID (e.g., "PRD")
        
        Returns:
            System dict or None if not found
        
        Example:
            >>> system = service.get_system_by_sid("PRD")
            >>> print(system['sid'], system['system_type'])
        """
        query_result = SAPQueryTemplates.get_system_by_sid(sid)
        
        result = self.project_manager.query(
            query_result.query,
            query_result.parameters
        )
        
        if result.result_set and len(result.result_set) > 0:
            # Convert result to dict
            node = result.result_set[0][0]
            system_dict = dict(node.properties)
            
            logger.debug("system_retrieved", sid=sid)
            return system_dict
        
        logger.debug("system_not_found", sid=sid)
        return None
    
    def get_all_systems(self) -> List[Dict]:
        """
        Get all systems in the landscape.
        
        Returns:
            List of system dicts
        """
        builder = QueryBuilder()
        query_result = builder.match_nodes("SAPSystem").return_nodes().build()
        
        result = self.project_manager.query(
            query_result.query,
            query_result.parameters
        )
        
        systems = []
        if result.result_set:
            for row in result.result_set:
                node = row[0]
                system_dict = dict(node.properties)
                systems.append(system_dict)
        
        logger.debug("systems_retrieved", count=len(systems))
        return systems
    
    def get_production_systems(self) -> List[Dict]:
        """
        Get all production systems (landscape_tier = PRD).
        
        Returns:
            List of production system dicts
        """
        query_result = SAPQueryTemplates.get_production_systems()
        
        result = self.project_manager.query(
            query_result.query,
            query_result.parameters
        )
        
        systems = []
        if result.result_set:
            for row in result.result_set:
                node = row[0]
                system_dict = dict(node.properties)
                systems.append(system_dict)
        
        logger.debug("production_systems_retrieved", count=len(systems))
        return systems
    
    def get_system_instances(self, sid: str) -> List[Dict]:
        """
        Get all instances for a system.
        
        Args:
            sid: System ID
        
        Returns:
            List of instance dicts
        """
        query_result = SAPQueryTemplates.get_system_instances(sid)
        
        result = self.project_manager.query(
            query_result.query,
            query_result.parameters
        )
        
        instances = []
        if result.result_set:
            for row in result.result_set:
                # Extract both system and instance
                inst_node = row[1]
                instance_dict = dict(inst_node.properties)
                instance_dict['sid'] = sid  # Add SID for reference
                instances.append(instance_dict)
        
        logger.debug("instances_retrieved", sid=sid, count=len(instances))
        return instances
    
    def get_all_instances(self) -> List[Dict]:
        """
        Get all instances across all systems.
        
        Returns:
            List of instance dicts
        """
        builder = QueryBuilder()
        query_result = builder \
            .match_nodes("SAPSystem", alias="sys") \
            .match_relationship("HAS_INSTANCE", "SAPInstance", target_alias="inst") \
            .return_nodes(["sys", "inst"]) \
            .build()
        
        result = self.project_manager.query(
            query_result.query,
            query_result.parameters
        )
        
        instances = []
        if result.result_set:
            for row in result.result_set:
                sys_node = row[0]
                inst_node = row[1]
                
                instance_dict = dict(inst_node.properties)
                instance_dict['sid'] = sys_node.properties.get('sid')
                instances.append(instance_dict)
        
        logger.debug("all_instances_retrieved", count=len(instances))
        return instances
    
    def get_hosts(self) -> List[Dict]:
        """
        Get all hosts in the landscape.
        
        Returns:
            List of host dicts
        """
        builder = QueryBuilder()
        query_result = builder.match_nodes("Host").return_nodes().build()
        
        result = self.project_manager.query(
            query_result.query,
            query_result.parameters
        )
        
        hosts = []
        if result.result_set:
            for row in result.result_set:
                node = row[0]
                host_dict = dict(node.properties)
                hosts.append(host_dict)
        
        logger.debug("hosts_retrieved", count=len(hosts))
        return hosts
    
    # =========================================================================
    # PORT OPERATIONS (Uses port_calculator.py)
    # =========================================================================
    
    def calculate_instance_ports(
        self,
        instance_number: str,
        instance_type: str
    ) -> Dict[str, int]:
        """
        Calculate all ports for an instance.
        
        Args:
            instance_number: Instance number (e.g., "00")
            instance_type: Instance type (PAS, AAS, ASCS, HDB)
        
        Returns:
            Dict of port names to port numbers
        
        Example:
            >>> ports = service.calculate_instance_ports("00", "PAS")
            >>> print(ports)
            {'dispatcher': 3200, 'gateway': 3300, 'http': 8000, ...}
        """
        return calculate_instance_ports(instance_number, instance_type)
    
    def find_port_conflicts(self) -> List[PortConflict]:
        """
        Find port conflicts across all instances.
        
        Calculates ports for all instances and detects collisions.
        
        Returns:
            List of PortConflict objects
        """
        conflicts = []
        
        # Get all instances
        instances = self.get_all_instances()
        
        # Calculate ports for each instance
        instance_ports = {}
        for instance in instances:
            instance_number = instance.get('instance_number')
            instance_type = instance.get('instance_type')
            
            if not instance_number or not instance_type:
                continue
            
            ports = self.calculate_instance_ports(instance_number, instance_type)
            instance_id = f"{instance.get('sid')}_{instance_number}"
            instance_ports[instance_id] = {
                'instance': instance,
                'ports': ports
            }
        
        # Check for conflicts
        port_usage = {}  # port -> list of instance_ids
        
        for instance_id, data in instance_ports.items():
            for port_name, port in data['ports'].items():
                if port not in port_usage:
                    port_usage[port] = []
                port_usage[port].append({
                    'instance_id': instance_id,
                    'instance': data['instance'],
                    'port_name': port_name
                })
        
        # Find conflicts (ports used by multiple instances)
        for port, users in port_usage.items():
            if len(users) > 1:
                # Create conflict for each pair
                for i in range(len(users)):
                    for j in range(i + 1, len(users)):
                        conflict = PortConflict(
                            port=port,
                            instance1=users[i]['instance'],
                            instance2=users[j]['instance'],
                            severity="HIGH"
                        )
                        conflicts.append(conflict)
                        
                        logger.warning(
                            "port_conflict_detected",
                            port=port,
                            instance1=users[i]['instance_id'],
                            instance2=users[j]['instance_id']
                        )
        
        return conflicts
    
    # =========================================================================
    # DEPENDENCY OPERATIONS (Uses dependency_rules.py)
    # =========================================================================
    
    def get_startup_sequence(self, sid: Optional[str] = None) -> StartupSequence:
        """
        Get recommended startup sequence for instances.
        
        Args:
            sid: Optional system ID (if None, returns sequence for all instances)
        
        Returns:
            StartupSequence object with ordered stages
        """
        if sid:
            instances = self.get_system_instances(sid)
        else:
            instances = self.get_all_instances()
        
        sequence = self.dependency_validator.generate_startup_sequence(instances)
        
        logger.info(
            "startup_sequence_generated",
            sid=sid,
            stages=len(sequence.sequence),
            total_instances=len(instances)
        )
        
        return sequence
    
    def validate_dependencies(self) -> List[DependencyRule]:
        """
        Validate all instance dependencies.
        
        Returns:
            List of violated dependency rules
        """
        instances = self.get_all_instances()
        violations = self.dependency_validator.validate_all_dependencies(instances)
        
        logger.info(
            "dependencies_validated",
            total_instances=len(instances),
            violations=len(violations)
        )
        
        return violations
    
    # =========================================================================
    # VALIDATION OPERATIONS (Uses validators.py)
    # =========================================================================
    
    def validate_landscape(self) -> ValidationResult:
        """
        Comprehensive landscape validation.
        
        Checks:
        - SID uniqueness
        - Port conflicts
        - Missing dependencies
        - Data completeness
        
        Returns:
            ValidationResult with all checks
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        
        systems = self.get_all_systems()
        
        # Check SID uniqueness
        sid_check = validate_sid_uniqueness(systems)
        if not sid_check.is_valid:
            result.errors.extend(sid_check.errors)
            result.is_valid = False
        result.warnings.extend(sid_check.warnings)
        
        # Check port conflicts
        conflicts = self.find_port_conflicts()
        if conflicts:
            for conflict in conflicts:
                result.add_error(str(conflict))
        
        # Check dependencies
        dep_violations = self.validate_dependencies()
        if dep_violations:
            for violation in dep_violations:
                result.add_warning(str(violation))
        
        logger.info(
            "landscape_validated",
            is_valid=result.is_valid,
            errors=len(result.errors),
            warnings=len(result.warnings)
        )
        
        return result
    
    def get_landscape_health(self) -> LandscapeHealth:
        """
        Get overall landscape health status.
        
        Returns:
            LandscapeHealth object with metrics
        """
        systems = self.get_all_systems()
        instances = self.get_all_instances()
        
        # Get validation results
        validation = self.validate_landscape()
        port_conflicts = self.find_port_conflicts()
        dep_violations = self.validate_dependencies()
        
        # Count active systems
        active_systems = sum(
            1 for s in systems
            if s.get('status', 'ACTIVE') == 'ACTIVE'
        )
        
        # Calculate health score
        # Start at 1.0, deduct for issues
        score = 1.0
        
        # Major issues (errors)
        score -= len(validation.errors) * 0.1
        score -= len(port_conflicts) * 0.05
        
        # Minor issues (warnings)
        score -= len(validation.warnings) * 0.02
        
        # Critical dependency violations
        critical_deps = [d for d in dep_violations if d.is_critical]
        score -= len(critical_deps) * 0.08
        
        # Clamp to 0.0 - 1.0
        score = max(0.0, min(1.0, score))
        
        health = LandscapeHealth(
            total_systems=len(systems),
            total_instances=len(instances),
            active_systems=active_systems,
            port_conflicts=port_conflicts,
            missing_dependencies=dep_violations,
            validation_errors=validation.errors,
            validation_warnings=validation.warnings,
            health_score=score
        )
        
        logger.info(
            "landscape_health_calculated",
            health_score=score,
            systems=len(systems),
            instances=len(instances)
        )
        
        return health
    
    # =========================================================================
    # STATISTICS & REPORTING
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get landscape statistics.
        
        Returns:
            Dict with various metrics
        """
        systems = self.get_all_systems()
        instances = self.get_all_instances()
        hosts = self.get_hosts()
        
        # Count by type
        systems_by_tier = {}
        for system in systems:
            tier = system.get('landscape_tier', 'UNKNOWN')
            systems_by_tier[tier] = systems_by_tier.get(tier, 0) + 1
        
        instances_by_type = {}
        for instance in instances:
            inst_type = instance.get('instance_type', 'UNKNOWN')
            instances_by_type[inst_type] = instances_by_type.get(inst_type, 0) + 1
        
        stats = {
            'total_systems': len(systems),
            'total_instances': len(instances),
            'total_hosts': len(hosts),
            'systems_by_tier': systems_by_tier,
            'instances_by_type': instances_by_type,
            'project_id': self.project_id,
            'generated_at': datetime.now().isoformat()
        }
        
        logger.debug("statistics_generated", project_id=self.project_id)
        
        return stats
    
    def generate_report(self) -> str:
        """
        Generate human-readable landscape report.
        
        Returns:
            Formatted report string
        """
        stats = self.get_statistics()
        health = self.get_landscape_health()
        
        report = []
        report.append("=" * 70)
        report.append(f"SAP LANDSCAPE REPORT - {self.project_id}")
        report.append("=" * 70)
        report.append("")
        
        # Overview
        report.append("OVERVIEW")
        report.append("-" * 70)
        report.append(f"Systems: {stats['total_systems']}")
        report.append(f"Instances: {stats['total_instances']}")
        report.append(f"Hosts: {stats['total_hosts']}")
        report.append("")
        
        # Health
        report.append("HEALTH STATUS")
        report.append("-" * 70)
        report.append(str(health))
        report.append("")
        
        # Systems by tier
        if stats['systems_by_tier']:
            report.append("SYSTEMS BY TIER")
            report.append("-" * 70)
            for tier, count in sorted(stats['systems_by_tier'].items()):
                report.append(f"  {tier}: {count}")
            report.append("")
        
        # Instances by type
        if stats['instances_by_type']:
            report.append("INSTANCES BY TYPE")
            report.append("-" * 70)
            for inst_type, count in sorted(stats['instances_by_type'].items()):
                report.append(f"  {inst_type}: {count}")
            report.append("")
        
        # Issues
        if health.validation_errors:
            report.append("ERRORS")
            report.append("-" * 70)
            for error in health.validation_errors[:5]:  # Top 5
                report.append(f"  ❌ {error}")
            if len(health.validation_errors) > 5:
                report.append(f"  ... and {len(health.validation_errors) - 5} more")
            report.append("")
        
        if health.port_conflicts:
            report.append("PORT CONFLICTS")
            report.append("-" * 70)
            for conflict in health.port_conflicts[:5]:  # Top 5
                report.append(f"  ⚠️  {conflict}")
            if len(health.port_conflicts) > 5:
                report.append(f"  ... and {len(health.port_conflicts) - 5} more")
            report.append("")
        
        report.append("=" * 70)
        report.append(f"Generated: {stats['generated_at']}")
        report.append("=" * 70)
        
        return "\n".join(report)


# Convenience function
def create_knowledge_service(project_manager, project_id: str) -> SAPKnowledgeService:
    """
    Create and initialize a SAP Knowledge Service.
    
    Args:
        project_manager: ProjectContextManager instance
        project_id: Project to work with
    
    Returns:
        Initialized SAPKnowledgeService
    
    Example:
        >>> service = create_knowledge_service(manager, "client_acme")
        >>> systems = service.get_all_systems()
    """
    return SAPKnowledgeService(project_manager, project_id)
