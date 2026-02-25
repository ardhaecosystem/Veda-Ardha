"""
Veda 4.0 - SAP Instance Dependency Rules
Encodes SAP startup/shutdown order rules and dependency relationships.

SAP STARTUP ORDER (Standard):
1. Database (HDB) - Must be first
2. Central Services (ASCS/SCS) - Enqueue + Message Server
3. Primary Application Server (PAS) - First app server
4. Additional Application Servers (AAS) - Can start in parallel
5. Gateway, Web Dispatcher - Last (if standalone)

CRITICAL RULES:
- Database MUST be running before any SAP instances
- ASCS MUST be running before PAS/AAS (provides enqueue service)
- PAS should start before AAS (but not strictly required)
- ERS (Enqueue Replication Server) is a failover for ASCS

PURPOSE:
- Guide troubleshooting ("PAS won't start? Check ASCS!")
- Generate startup/shutdown scripts
- Validate landscape configurations
- Auto-remediate startup issues
"""

from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import IntEnum

import structlog

logger = structlog.get_logger()


class StartupPriority(IntEnum):
    """
    Standard SAP startup priorities.
    Lower number = starts earlier.
    """
    DATABASE = 1          # HDB, Oracle, etc. - MUST be first
    CENTRAL_SERVICES = 2  # ASCS, SCS - Enqueue + Message Server
    ERS = 2              # ERS (same priority as ASCS, different order)
    PRIMARY_APP = 3       # PAS - First application server
    ADDITIONAL_APP = 4    # AAS - Additional app servers
    GATEWAY = 5          # Standalone Gateway (if not in PAS)
    WEB_DISPATCHER = 5   # Web Dispatcher
    UNKNOWN = 99         # Fallback


@dataclass
class DependencyRule:
    """
    Represents a dependency between two instance types.
    
    Example:
        PAS depends on ASCS (PAS cannot start without ASCS running)
    """
    dependent: str              # Instance type that has the dependency
    required: str               # Instance type that must be running first
    dependency_type: str        # Type of dependency (startup, enqueue, database)
    is_critical: bool = True    # If False, soft dependency (warning only)
    reason: str = ""            # Human-readable explanation
    
    def __str__(self) -> str:
        criticality = "CRITICAL" if self.is_critical else "SOFT"
        return f"[{criticality}] {self.dependent} requires {self.required}: {self.reason}"


@dataclass
class StartupSequence:
    """
    Complete startup sequence for a system.
    """
    sequence: List[List[str]] = field(default_factory=list)  # Stages, each with instance IDs
    warnings: List[str] = field(default_factory=list)
    
    def add_stage(self, instances: List[str]):
        """Add a startup stage (instances that can start in parallel)."""
        self.sequence.append(instances)
    
    def get_flat_order(self) -> List[str]:
        """Get flattened list of all instances in order."""
        return [inst for stage in self.sequence for inst in stage]
    
    def get_stage_for_instance(self, instance_id: str) -> Optional[int]:
        """Get which startup stage an instance is in (0-indexed)."""
        for i, stage in enumerate(self.sequence):
            if instance_id in stage:
                return i
        return None


class DependencyValidator:
    """
    Validates SAP instance dependencies and generates startup sequences.
    """
    
    # Core dependency rules (based on SAP best practices)
    CORE_RULES = [
        DependencyRule(
            dependent="ASCS",
            required="HDB",
            dependency_type="database",
            is_critical=True,
            reason="ASCS requires database for enqueue table and message server persistence"
        ),
        DependencyRule(
            dependent="PAS",
            required="HDB",
            dependency_type="database",
            is_critical=True,
            reason="Application server requires database connection"
        ),
        DependencyRule(
            dependent="AAS",
            required="HDB",
            dependency_type="database",
            is_critical=True,
            reason="Application server requires database connection"
        ),
        DependencyRule(
            dependent="PAS",
            required="ASCS",
            dependency_type="enqueue",
            is_critical=True,
            reason="PAS requires ASCS for enqueue service and message server"
        ),
        DependencyRule(
            dependent="AAS",
            required="ASCS",
            dependency_type="enqueue",
            is_critical=True,
            reason="AAS requires ASCS for enqueue service and message server"
        ),
        DependencyRule(
            dependent="AAS",
            required="PAS",
            dependency_type="startup",
            is_critical=False,
            reason="PAS should start before AAS (soft recommendation)"
        ),
        DependencyRule(
            dependent="ERS",
            required="HDB",
            dependency_type="database",
            is_critical=True,
            reason="ERS requires database for enqueue replication table"
        ),
    ]
    
    def __init__(self):
        self.rules = self.CORE_RULES.copy()
        logger.info("dependency_validator_initialized", rule_count=len(self.rules))
    
    def get_startup_priority(self, instance_type: str) -> int:
        """
        Get standard startup priority for instance type.
        
        Args:
            instance_type: Instance type (HDB, ASCS, PAS, AAS, etc.)
            
        Returns:
            Priority number (1=first, higher=later)
        """
        priority_map = {
            "HDB": StartupPriority.DATABASE,
            "Oracle": StartupPriority.DATABASE,
            "DB2": StartupPriority.DATABASE,
            "ASCS": StartupPriority.CENTRAL_SERVICES,
            "SCS": StartupPriority.CENTRAL_SERVICES,
            "ERS": StartupPriority.ERS,
            "PAS": StartupPriority.PRIMARY_APP,
            "Central": StartupPriority.PRIMARY_APP,
            "AAS": StartupPriority.ADDITIONAL_APP,
            "Gateway": StartupPriority.GATEWAY,
            "WebDisp": StartupPriority.WEB_DISPATCHER,
        }
        
        return priority_map.get(instance_type, StartupPriority.UNKNOWN)
    
    def get_dependencies(self, instance_type: str, critical_only: bool = False) -> List[DependencyRule]:
        """
        Get all dependencies for an instance type.
        
        Args:
            instance_type: Instance type to check
            critical_only: If True, only return critical dependencies
            
        Returns:
            List of dependency rules
        """
        deps = [rule for rule in self.rules if rule.dependent == instance_type]
        
        if critical_only:
            deps = [d for d in deps if d.is_critical]
        
        return deps
    
    def check_can_start(
        self,
        instance_type: str,
        running_instances: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Check if an instance can start given currently running instances.
        
        Args:
            instance_type: Type of instance trying to start
            running_instances: List of instance types already running
            
        Returns:
            Tuple of (can_start, missing_dependencies)
            
        Example:
            >>> validator = DependencyValidator()
            >>> can_start, missing = validator.check_can_start("PAS", ["HDB", "ASCS"])
            >>> print(can_start)  # True
            >>> can_start, missing = validator.check_can_start("PAS", ["HDB"])
            >>> print(can_start)  # False
            >>> print(missing)    # ["ASCS"]
        """
        dependencies = self.get_dependencies(instance_type, critical_only=True)
        missing = []
        
        for dep in dependencies:
            if dep.required not in running_instances:
                missing.append(dep.required)
        
        can_start = len(missing) == 0
        
        if not can_start:
            logger.warning(
                "instance_cannot_start",
                instance_type=instance_type,
                missing_dependencies=missing
            )
        
        return can_start, missing
    
    def generate_startup_sequence(
        self,
        instances: Dict[str, str]  # {instance_id: instance_type}
    ) -> StartupSequence:
        """
        Generate optimal startup sequence for a set of instances.
        
        Args:
            instances: Dict mapping instance IDs to types
                      e.g., {"HDB00": "HDB", "ASCS01": "ASCS", "PAS00": "PAS"}
            
        Returns:
            StartupSequence with stages and warnings
            
        Example:
            >>> instances = {"HDB00": "HDB", "ASCS01": "ASCS", "PAS00": "PAS", "AAS10": "AAS"}
            >>> sequence = validator.generate_startup_sequence(instances)
            >>> print(sequence.sequence)
            [["HDB00"], ["ASCS01"], ["PAS00"], ["AAS10"]]
        """
        sequence = StartupSequence()
        
        # Group instances by priority
        priority_groups: Dict[int, List[str]] = {}
        
        for instance_id, instance_type in instances.items():
            priority = self.get_startup_priority(instance_type)
            
            if priority not in priority_groups:
                priority_groups[priority] = []
            
            priority_groups[priority].append(instance_id)
        
        # Sort by priority and add stages
        for priority in sorted(priority_groups.keys()):
            stage = priority_groups[priority]
            sequence.add_stage(stage)
            
            logger.debug(
                "startup_stage_added",
                priority=priority,
                instances=stage
            )
        
        # Check for potential issues
        sequence.warnings = self._validate_sequence(instances, sequence)
        
        logger.info(
            "startup_sequence_generated",
            stage_count=len(sequence.sequence),
            total_instances=len(instances),
            warnings=len(sequence.warnings)
        )
        
        return sequence
    
    def _validate_sequence(
        self,
        instances: Dict[str, str],
        sequence: StartupSequence
    ) -> List[str]:
        """
        Validate a startup sequence for potential issues.
        
        Returns:
            List of warning messages
        """
        warnings = []
        instance_types = set(instances.values())
        
        # Check 1: Database present?
        has_db = any(t in instance_types for t in ["HDB", "Oracle", "DB2"])
        if not has_db:
            warnings.append("No database instance found - system may not start properly")
        
        # Check 2: ASCS present if PAS/AAS present?
        has_app = any(t in instance_types for t in ["PAS", "AAS", "Central"])
        has_ascs = any(t in instance_types for t in ["ASCS", "SCS"])
        
        if has_app and not has_ascs:
            warnings.append("Application servers present but no ASCS - system will not start")
        
        # Check 3: Multiple databases?
        db_count = sum(1 for t in instance_types if t in ["HDB", "Oracle", "DB2"])
        if db_count > 1:
            warnings.append(f"Multiple database types detected ({db_count}) - unusual configuration")
        
        return warnings
    
    def generate_shutdown_sequence(
        self,
        instances: Dict[str, str]
    ) -> StartupSequence:
        """
        Generate shutdown sequence (reverse of startup).
        
        Shutdown order is opposite of startup:
        1. Gateway, Web Dispatcher
        2. AAS
        3. PAS
        4. ASCS/ERS
        5. Database (last!)
        
        Args:
            instances: Dict mapping instance IDs to types
            
        Returns:
            StartupSequence (but for shutdown)
        """
        startup = self.generate_startup_sequence(instances)
        
        # Reverse the sequence
        shutdown = StartupSequence()
        shutdown.sequence = list(reversed(startup.sequence))
        shutdown.warnings = startup.warnings
        
        logger.info(
            "shutdown_sequence_generated",
            stage_count=len(shutdown.sequence)
        )
        
        return shutdown
    
    def explain_startup_failure(
        self,
        failed_instance_type: str,
        running_instances: List[str]
    ) -> str:
        """
        Generate human-readable explanation for why an instance can't start.
        
        Args:
            failed_instance_type: Type that failed to start
            running_instances: Types currently running
            
        Returns:
            Explanation string
        """
        can_start, missing = self.check_can_start(failed_instance_type, running_instances)
        
        if can_start:
            return f"{failed_instance_type} should be able to start (all dependencies met)"
        
        # Build explanation
        explanation_parts = [
            f"❌ {failed_instance_type} cannot start because these dependencies are missing:",
            ""
        ]
        
        for missing_type in missing:
            # Find the rule explaining why
            rules = [r for r in self.rules if r.dependent == failed_instance_type and r.required == missing_type]
            
            if rules:
                rule = rules[0]
                explanation_parts.append(f"  • {missing_type}: {rule.reason}")
            else:
                explanation_parts.append(f"  • {missing_type}: Required dependency")
        
        explanation_parts.extend([
            "",
            "✅ Action items:",
            f"1. Start {missing[0]} first",
            f"2. Verify {missing[0]} is GREEN (healthy)",
            f"3. Then retry starting {failed_instance_type}"
        ])
        
        return "\n".join(explanation_parts)
    
    def detect_circular_dependencies(self) -> List[str]:
        """
        Detect circular dependency chains.
        
        Returns:
            List of circular dependency descriptions (empty if none)
        """
        # Build dependency graph
        graph: Dict[str, Set[str]] = {}
        
        for rule in self.rules:
            if rule.dependent not in graph:
                graph[rule.dependent] = set()
            graph[rule.dependent].add(rule.required)
        
        # DFS to detect cycles
        def has_cycle(node: str, visited: Set[str], rec_stack: Set[str]) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    cycle = has_cycle(neighbor, visited, rec_stack)
                    if cycle:
                        return [node] + cycle
                elif neighbor in rec_stack:
                    return [node, neighbor]
            
            rec_stack.remove(node)
            return None
        
        cycles = []
        visited: Set[str] = set()
        
        for node in graph:
            if node not in visited:
                cycle = has_cycle(node, visited, set())
                if cycle:
                    cycles.append(" → ".join(cycle))
        
        if cycles:
            logger.error("circular_dependencies_detected", cycles=cycles)
        
        return cycles


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_standard_startup_sequence() -> List[Tuple[int, str, str]]:
    """
    Get the standard SAP startup sequence with priorities.
    
    Returns:
        List of (priority, instance_type, description) tuples
    """
    return [
        (1, "HDB/Oracle/DB2", "Database - Must start first"),
        (2, "ASCS/SCS", "Central Services - Enqueue + Message Server"),
        (2, "ERS", "Enqueue Replication Server (HA failover)"),
        (3, "PAS/Central", "Primary Application Server"),
        (4, "AAS", "Additional Application Servers (parallel)"),
        (5, "Gateway", "Standalone Gateway (if not in PAS)"),
        (5, "WebDisp", "Web Dispatcher"),
    ]


def create_troubleshooting_guide(instance_type: str) -> str:
    """
    Generate a troubleshooting guide for common startup issues.
    
    Args:
        instance_type: Type of instance having issues
        
    Returns:
        Markdown-formatted troubleshooting guide
    """
    validator = DependencyValidator()
    dependencies = validator.get_dependencies(instance_type, critical_only=True)
    
    guide_parts = [
        f"# {instance_type} Startup Troubleshooting Guide",
        "",
        "## Prerequisites",
        ""
    ]
    
    if dependencies:
        guide_parts.append("This instance requires:")
        for dep in dependencies:
            guide_parts.append(f"- ✅ **{dep.required}**: {dep.reason}")
    else:
        guide_parts.append("No prerequisites (can start independently)")
    
    guide_parts.extend([
        "",
        "## Startup Checklist",
        "",
        "1. **Check database connection**",
        "   ```bash",
        "   R3trans -d  # Test database connectivity",
        "   ```",
        "",
        "2. **Verify prerequisites are running**",
        "   ```bash",
        "   sapcontrol -nr <instance> -function GetProcessList",
        "   ```",
        "",
        "3. **Check for port conflicts**",
        "   ```bash",
        "   netstat -an | grep <port>",
        "   ```",
        "",
        "4. **Review logs**",
        "   - Work process logs: `/usr/sap/<SID>/<instance>/work/dev_*`",
        "   - System log: SM21",
        "   - Instance profile: RZ10",
        "",
        "## Common Issues",
        "",
        "- **Enqueue service not available**: Ensure ASCS is running",
        "- **Message server connection failed**: Check ASCS and network",
        "- **Database connection failed**: Verify DB is up and R3trans works",
        "- **Port already in use**: Check for zombie processes or conflicts"
    ])
    
    return "\n".join(guide_parts)


# End of Dependency Rules implementation
