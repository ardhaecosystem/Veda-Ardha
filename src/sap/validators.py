"""
Veda 4.0 - SAP Validation Utilities
Standalone validation functions for SAP landscape data.

DIFFERENCE FROM ontology.py VALIDATORS:
- ontology.py: Pydantic field validators (single entity validation)
- validators.py: Cross-entity validation (uniqueness, conflicts, completeness)

USE CASES:
- Batch validation: Validate 100 systems before importing
- Uniqueness checks: No duplicate SIDs across landscape
- Conflict detection: Port conflicts, instance number collisions
- Data quality: Score completeness of landscape data
- Pre-flight checks: Validate before graph insertion

These are utility functions, not tied to Pydantic models.
"""

from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
import re

import structlog

# Import from our ontology for type checking
from .ontology import SAPSystem, SAPInstance, Host

logger = structlog.get_logger()


@dataclass
class ValidationResult:
    """
    Result of a validation check.
    """
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    info: Dict[str, any] = None
    
    def __post_init__(self):
        if self.info is None:
            self.info = {}
    
    def add_error(self, message: str):
        """Add an error message."""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str):
        """Add a warning message."""
        self.warnings.append(message)
    
    def __str__(self) -> str:
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        parts = [status]
        
        if self.errors:
            parts.append(f"Errors: {len(self.errors)}")
        if self.warnings:
            parts.append(f"Warnings: {len(self.warnings)}")
        
        return " | ".join(parts)


# =============================================================================
# SID VALIDATION
# =============================================================================

def validate_sid_uniqueness(systems: List[Dict]) -> ValidationResult:
    """
    Validate that all SIDs are unique across systems.
    
    Args:
        systems: List of system dicts with 'sid' field
        
    Returns:
        ValidationResult with uniqueness check
        
    Example:
        >>> systems = [
        ...     {"sid": "PRD", "system_type": "S/4HANA"},
        ...     {"sid": "QAS", "system_type": "ECC"},
        ...     {"sid": "PRD", "system_type": "BW"}  # Duplicate!
        ... ]
        >>> result = validate_sid_uniqueness(systems)
        >>> print(result.is_valid)  # False
        >>> print(result.errors)    # ["Duplicate SID 'PRD' found 2 times"]
    """
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    
    # Count SID occurrences
    sid_counts: Dict[str, int] = {}
    
    for system in systems:
        sid = system.get("sid", "").upper()
        if not sid:
            result.add_warning("System found without SID")
            continue
        
        sid_counts[sid] = sid_counts.get(sid, 0) + 1
    
    # Find duplicates
    duplicates = {sid: count for sid, count in sid_counts.items() if count > 1}
    
    if duplicates:
        for sid, count in duplicates.items():
            result.add_error(f"Duplicate SID '{sid}' found {count} times")
        
        logger.error("sid_uniqueness_check_failed", duplicates=duplicates)
    else:
        logger.debug("sid_uniqueness_check_passed", unique_sids=len(sid_counts))
    
    result.info["unique_sids"] = len(sid_counts)
    result.info["duplicates"] = list(duplicates.keys())
    
    return result


def validate_sid_format_batch(sids: List[str]) -> ValidationResult:
    """
    Batch validate SID formats.
    
    Faster than validating through Pydantic models when you just need format checks.
    
    Args:
        sids: List of SID strings to validate
        
    Returns:
        ValidationResult with format validation
    """
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    
    # Reserved words (copied from ontology.py for independence)
    reserved = {
        'ADD', 'ALL', 'AMD', 'AND', 'ANY', 'ARE', 'ASC', 'AUX', 
        'AVG', 'BIN', 'BIT', 'CDC', 'COM', 'CON', 'DAT', 'DBA',
        'DBM', 'DBO', 'END', 'EPS', 'FOR', 'GET', 'GID', 'IBM',
        'INT', 'KEY', 'LOG', 'LPT', 'MAP', 'MAX', 'MEM', 'MIN',
        'MON', 'NIX', 'NOT', 'NUL', 'OFF', 'OLD', 'OMS', 'OUT',
        'PAD', 'PRN', 'RAW', 'REF', 'ROW', 'SAP', 'SET', 'SGA',
        'SHG', 'SID', 'SQL', 'SUM', 'SYS', 'TMP', 'TOP', 'TRC',
        'UID', 'USE', 'USR', 'VAR', 'VIA'
    }
    
    invalid_sids = []
    
    for sid in sids:
        sid = sid.upper()
        
        # Check length
        if len(sid) != 3:
            result.add_error(f"SID '{sid}': Must be exactly 3 characters")
            invalid_sids.append(sid)
            continue
        
        # Must start with letter
        if not sid[0].isalpha():
            result.add_error(f"SID '{sid}': Must start with a letter")
            invalid_sids.append(sid)
            continue
        
        # Only alphanumeric
        if not sid.isalnum():
            result.add_error(f"SID '{sid}': Must be alphanumeric")
            invalid_sids.append(sid)
            continue
        
        # Reserved words
        if sid in reserved:
            result.add_error(f"SID '{sid}': Reserved word (cannot be used)")
            invalid_sids.append(sid)
            continue
    
    result.info["total_sids"] = len(sids)
    result.info["invalid_sids"] = invalid_sids
    result.info["valid_count"] = len(sids) - len(invalid_sids)
    
    if result.is_valid:
        logger.debug("batch_sid_validation_passed", valid_count=len(sids))
    else:
        logger.warning("batch_sid_validation_failed", invalid_count=len(invalid_sids))
    
    return result


# =============================================================================
# INSTANCE NUMBER VALIDATION
# =============================================================================

def validate_instance_number_uniqueness(
    instances: List[Dict],
    per_host: bool = True
) -> ValidationResult:
    """
    Validate instance number uniqueness.
    
    Args:
        instances: List of instance dicts with 'instance_number' and 'host' fields
        per_host: If True, check uniqueness per host (standard SAP rule)
                  If False, check uniqueness globally (stricter)
        
    Returns:
        ValidationResult with uniqueness check
        
    SAP RULE: On a single host, each instance number must be unique.
    Example: Can't have ASCS01 and PAS01 on the same host (both use 01)
    """
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    
    if per_host:
        # Check uniqueness per host
        host_instances: Dict[str, List[str]] = {}
        
        for inst in instances:
            host = inst.get("host", "unknown")
            inst_num = inst.get("instance_number", "")
            inst_type = inst.get("instance_type", "unknown")
            
            if not inst_num:
                result.add_warning(f"Instance {inst_type} has no instance number")
                continue
            
            if host not in host_instances:
                host_instances[host] = []
            
            host_instances[host].append((inst_num, inst_type))
        
        # Find duplicates per host
        for host, inst_list in host_instances.items():
            inst_nums = [num for num, _ in inst_list]
            duplicates = {num for num in inst_nums if inst_nums.count(num) > 1}
            
            if duplicates:
                for dup_num in duplicates:
                    types = [t for n, t in inst_list if n == dup_num]
                    result.add_error(
                        f"Host '{host}': Instance number {dup_num} used by {len(types)} instances ({', '.join(types)})"
                    )
    
    else:
        # Check global uniqueness (stricter - not standard SAP)
        inst_counts: Dict[str, int] = {}
        
        for inst in instances:
            inst_num = inst.get("instance_number", "")
            if inst_num:
                inst_counts[inst_num] = inst_counts.get(inst_num, 0) + 1
        
        duplicates = {num: count for num, count in inst_counts.items() if count > 1}
        
        if duplicates:
            for num, count in duplicates.items():
                result.add_warning(
                    f"Instance number {num} used {count} times globally (allowed if on different hosts)"
                )
    
    return result


# =============================================================================
# HOSTNAME VALIDATION
# =============================================================================

def validate_hostname_format_batch(hostnames: List[str]) -> ValidationResult:
    """
    Batch validate hostname formats (RFC 1123).
    
    Args:
        hostnames: List of hostname strings
        
    Returns:
        ValidationResult with format validation
    """
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    
    # RFC 1123 pattern
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
    
    invalid_hostnames = []
    
    for hostname in hostnames:
        if not re.match(pattern, hostname):
            result.add_error(
                f"Hostname '{hostname}': Invalid format (must be alphanumeric with hyphens, "
                "1-63 characters, not start/end with hyphen)"
            )
            invalid_hostnames.append(hostname)
    
    result.info["total_hostnames"] = len(hostnames)
    result.info["invalid_hostnames"] = invalid_hostnames
    result.info["valid_count"] = len(hostnames) - len(invalid_hostnames)
    
    return result


# =============================================================================
# PORT CONFLICT DETECTION
# =============================================================================

def detect_port_conflicts(
    instances: List[Dict]  # {instance_type, instance_number, host}
) -> ValidationResult:
    """
    Detect port conflicts across instances.
    
    Uses port_calculator.py to compute ports, then checks for conflicts.
    
    Args:
        instances: List of instance dicts
        
    Returns:
        ValidationResult with conflict detection
    """
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    
    # Import here to avoid circular dependency
    try:
        from .port_calculator import calculate_instance_ports
    except ImportError as e:
        result.add_warning(f"Port calculator import failed: {str(e)}")
        result.info["hosts_checked"] = 0
        result.info["conflicts_found"] = 0
        logger.warning("port_calculator_import_failed", error=str(e))
        return result
    
    # Track ports by host
    host_ports: Dict[str, List[Tuple[int, str, str]]] = {}  # {host: [(port, inst_id, port_name)]}
    
    for inst in instances:
        inst_type = inst.get("instance_type")
        inst_num = inst.get("instance_number")
        host = inst.get("host", "unknown")
        
        if not inst_type or not inst_num:
            continue
        
        # Calculate ports for this instance
        # Returns InstancePorts object with .to_dict() method
        try:
            ports_obj = calculate_instance_ports(inst_num, inst_type)
            ports_dict = ports_obj.to_dict()  # Convert to dict
        except Exception as e:
            logger.warning("port_calculation_error", inst_type=inst_type, inst_num=inst_num, error=str(e))
            continue
        
        if host not in host_ports:
            host_ports[host] = []
        
        # Add all ports
        inst_id = f"{inst_type}{inst_num}"
        for port_name, port_num in ports_dict.items():
            host_ports[host].append((port_num, inst_id, port_name))
    
    # Find conflicts per host
    for host, port_list in host_ports.items():
        # Group by port number
        port_map: Dict[int, List[Tuple[str, str]]] = {}
        
        for port_num, inst_id, port_name in port_list:
            if port_num not in port_map:
                port_map[port_num] = []
            port_map[port_num].append((inst_id, port_name))
        
        # Find ports used by multiple instances
        for port_num, users in port_map.items():
            if len(users) > 1:
                user_desc = " vs ".join([f"{inst_id} ({name})" for inst_id, name in users])
                result.add_error(
                    f"Host '{host}': Port {port_num} conflict - {user_desc}"
                )
    
    result.info["hosts_checked"] = len(host_ports)
    result.info["conflicts_found"] = len(result.errors)
    
    if result.is_valid:
        logger.debug("no_port_conflicts", hosts=len(host_ports))
    else:
        logger.warning("port_conflicts_detected", conflicts=len(result.errors))
    
    return result


# =============================================================================
# LANDSCAPE COMPLETENESS
# =============================================================================

def validate_landscape_completeness(
    systems: List[Dict],
    instances: List[Dict]
) -> ValidationResult:
    """
    Validate that landscape has required components.
    
    Checks:
    - Each system has at least one instance
    - Application servers have ASCS
    - Systems have database reference
    
    Args:
        systems: List of system dicts
        instances: List of instance dicts (with 'system_sid' field)
        
    Returns:
        ValidationResult with completeness check
    """
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    
    # Build SID to instances mapping
    sid_instances: Dict[str, List[str]] = {}
    
    for inst in instances:
        sid = inst.get("system_sid", "").upper()
        inst_type = inst.get("instance_type", "unknown")
        
        if sid:
            if sid not in sid_instances:
                sid_instances[sid] = []
            sid_instances[sid].append(inst_type)
    
    # Check each system
    for system in systems:
        sid = system.get("sid", "").upper()
        
        if not sid:
            result.add_warning("System found without SID")
            continue
        
        # Check 1: Does system have any instances?
        if sid not in sid_instances or len(sid_instances[sid]) == 0:
            result.add_warning(f"System '{sid}': No instances defined")
            continue
        
        inst_types = sid_instances[sid]
        
        # Check 2: If has PAS/AAS, must have ASCS
        has_app = any(t in inst_types for t in ["PAS", "AAS", "Central"])
        has_ascs = any(t in inst_types for t in ["ASCS", "SCS"])
        
        if has_app and not has_ascs:
            result.add_error(
                f"System '{sid}': Has application servers ({', '.join([t for t in inst_types if t in ['PAS', 'AAS', 'Central']])}) "
                f"but missing ASCS/SCS (required for enqueue service)"
            )
        
        # Check 3: Has database instance?
        has_db = any(t in inst_types for t in ["HDB", "Oracle", "DB2"])
        
        if not has_db:
            result.add_warning(
                f"System '{sid}': No database instance found (instances: {', '.join(inst_types)})"
            )
    
    result.info["systems_checked"] = len(systems)
    result.info["instances_checked"] = len(instances)
    
    return result


# =============================================================================
# DATA QUALITY SCORING
# =============================================================================

@dataclass
class DataQualityScore:
    """Data quality score with breakdown."""
    overall_score: float  # 0.0 to 1.0
    completeness: float   # How complete is the data?
    correctness: float    # How correct is the data?
    consistency: float    # How consistent is the data?
    details: Dict[str, any]
    
    def get_grade(self) -> str:
        """Get letter grade (A-F)."""
        if self.overall_score >= 0.9:
            return "A"
        elif self.overall_score >= 0.8:
            return "B"
        elif self.overall_score >= 0.7:
            return "C"
        elif self.overall_score >= 0.6:
            return "D"
        else:
            return "F"


def calculate_data_quality(
    systems: List[Dict],
    instances: List[Dict],
    hosts: List[Dict]
) -> DataQualityScore:
    """
    Calculate data quality score for landscape data.
    
    Factors:
    - Completeness: % of required fields present
    - Correctness: % of data passing validation
    - Consistency: % of cross-entity checks passing
    
    Args:
        systems: List of system dicts
        instances: List of instance dicts
        hosts: List of host dicts
        
    Returns:
        DataQualityScore with breakdown
    """
    scores = {
        "completeness": 0.0,
        "correctness": 0.0,
        "consistency": 0.0
    }
    
    details = {}
    
    # 1. COMPLETENESS - Required fields present?
    required_system_fields = ["sid", "system_type", "landscape_tier"]
    required_instance_fields = ["instance_type", "instance_number"]
    required_host_fields = ["hostname"]
    
    system_completeness = sum(
        all(field in sys for field in required_system_fields)
        for sys in systems
    ) / max(len(systems), 1)
    
    instance_completeness = sum(
        all(field in inst for field in required_instance_fields)
        for inst in instances
    ) / max(len(instances), 1)
    
    host_completeness = sum(
        all(field in host for field in required_host_fields)
        for host in hosts
    ) / max(len(hosts), 1)
    
    scores["completeness"] = (
        system_completeness + instance_completeness + host_completeness
    ) / 3
    
    details["completeness"] = {
        "systems": f"{system_completeness:.1%}",
        "instances": f"{instance_completeness:.1%}",
        "hosts": f"{host_completeness:.1%}"
    }
    
    # 2. CORRECTNESS - Valid formats?
    sids = [s.get("sid", "") for s in systems if s.get("sid")]
    sid_validation = validate_sid_format_batch(sids)
    
    hostnames = [h.get("hostname", "") for h in hosts if h.get("hostname")]
    hostname_validation = validate_hostname_format_batch(hostnames)
    
    valid_sids = sid_validation.info.get("valid_count", 0)
    valid_hostnames = hostname_validation.info.get("valid_count", 0)
    
    scores["correctness"] = (
        (valid_sids / max(len(sids), 1)) +
        (valid_hostnames / max(len(hostnames), 1))
    ) / 2
    
    details["correctness"] = {
        "valid_sids": f"{valid_sids}/{len(sids)}",
        "valid_hostnames": f"{valid_hostnames}/{len(hostnames)}"
    }
    
    # 3. CONSISTENCY - Cross-entity checks?
    uniqueness_check = validate_sid_uniqueness(systems)
    completeness_check = validate_landscape_completeness(systems, instances)
    
    consistency_score = 1.0
    
    if not uniqueness_check.is_valid:
        consistency_score -= 0.3
    
    if not completeness_check.is_valid:
        consistency_score -= 0.3
    
    if len(completeness_check.warnings) > 0:
        consistency_score -= 0.2
    
    scores["consistency"] = max(0.0, consistency_score)
    
    details["consistency"] = {
        "unique_sids": uniqueness_check.is_valid,
        "complete_landscape": completeness_check.is_valid,
        "warnings": len(completeness_check.warnings)
    }
    
    # Calculate overall score
    overall = sum(scores.values()) / len(scores)
    
    return DataQualityScore(
        overall_score=overall,
        completeness=scores["completeness"],
        correctness=scores["correctness"],
        consistency=scores["consistency"],
        details=details
    )


# End of Validators implementation
