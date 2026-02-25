"""
Veda 4.0 - SAP Port Calculator
Calculates SAP port numbers based on instance numbers and instance types.

SAP uses predictable port formulas rather than storing ports redundantly.
This module implements all standard SAP port calculations.

Port Formulas:
- Message Server: 36NN (3600 + instance)
- Gateway: 33NN (3300 + instance)
- Dispatcher: 32NN (3200 + instance)
- HTTP: 80NN (8000 + instance)
- HTTPS: 443NN (44300 + instance)
- HANA SQL: 3NN15 (30015 + instance*100)
- HANA System DB: 3NN13 (30013 + instance*100)
- HANA Index Server: 3NN03 (30003 + instance*100)

Usage:
    >>> from src.sap.port_calculator import calculate_instance_ports
    >>> ports = calculate_instance_ports("00", "PAS")
    >>> print(ports)
    {'dispatcher': 3200, 'gateway': 3300, 'message_server': 3600, ...}
"""

from typing import Dict, List, Optional, Literal
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


# =============================================================================
# PORT CALCULATION FUNCTIONS
# =============================================================================

def calculate_dispatcher_port(instance_number: str) -> int:
    """
    Calculate SAP Dispatcher port.
    Formula: 32NN where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        Dispatcher port number
        
    Example:
        >>> calculate_dispatcher_port("00")
        3200
        >>> calculate_dispatcher_port("10")
        3210
    """
    instance = int(instance_number)
    return 3200 + instance


def calculate_gateway_port(instance_number: str) -> int:
    """
    Calculate SAP Gateway port.
    Formula: 33NN where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        Gateway port number
        
    Example:
        >>> calculate_gateway_port("00")
        3300
        >>> calculate_gateway_port("01")
        3301
    """
    instance = int(instance_number)
    return 3300 + instance


def calculate_message_server_port(instance_number: str) -> int:
    """
    Calculate SAP Message Server port.
    Formula: 36NN where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        Message Server port number
        
    Example:
        >>> calculate_message_server_port("01")
        3601
    """
    instance = int(instance_number)
    return 3600 + instance


def calculate_http_port(instance_number: str) -> int:
    """
    Calculate SAP HTTP port (ICM).
    Formula: 80NN where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        HTTP port number
        
    Example:
        >>> calculate_http_port("00")
        8000
        >>> calculate_http_port("10")
        8010
    """
    instance = int(instance_number)
    return 8000 + instance


def calculate_https_port(instance_number: str) -> int:
    """
    Calculate SAP HTTPS port (ICM).
    Formula: 443NN where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        HTTPS port number
        
    Example:
        >>> calculate_https_port("00")
        44300
        >>> calculate_https_port("10")
        44310
    """
    instance = int(instance_number)
    return 44300 + instance


def calculate_hana_sql_port(instance_number: str) -> int:
    """
    Calculate SAP HANA SQL port (tenant database).
    Formula: 3NN15 where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        HANA SQL port number
        
    Example:
        >>> calculate_hana_sql_port("00")
        30015
        >>> calculate_hana_sql_port("10")
        31015
    """
    instance = int(instance_number)
    return 30015 + (instance * 100)


def calculate_hana_systemdb_port(instance_number: str) -> int:
    """
    Calculate SAP HANA System DB port.
    Formula: 3NN13 where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        HANA System DB port number
        
    Example:
        >>> calculate_hana_systemdb_port("00")
        30013
        >>> calculate_hana_systemdb_port("90")
        39013
    """
    instance = int(instance_number)
    return 30013 + (instance * 100)


def calculate_hana_indexserver_port(instance_number: str) -> int:
    """
    Calculate SAP HANA Index Server internal port.
    Formula: 3NN03 where NN is the instance number
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        HANA Index Server port number
        
    Example:
        >>> calculate_hana_indexserver_port("00")
        30003
    """
    instance = int(instance_number)
    return 30003 + (instance * 100)


def calculate_enqueue_server_port(instance_number: str) -> int:
    """
    Calculate SAP Enqueue Server port (ASCS).
    Formula: 32NN where NN is the instance number
    
    Note: Same as dispatcher port for standalone enqueue.
    For ASCS, uses 3200 + instance.
    
    Args:
        instance_number: 2-digit instance number (00-99)
        
    Returns:
        Enqueue Server port number
        
    Example:
        >>> calculate_enqueue_server_port("01")
        3201
    """
    instance = int(instance_number)
    return 3200 + instance


# =============================================================================
# COMPREHENSIVE PORT CALCULATION
# =============================================================================

@dataclass
class InstancePorts:
    """Complete port mapping for an SAP instance."""
    instance_number: str
    instance_type: str
    dispatcher: Optional[int] = None
    gateway: Optional[int] = None
    message_server: Optional[int] = None
    http: Optional[int] = None
    https: Optional[int] = None
    hana_sql: Optional[int] = None
    hana_systemdb: Optional[int] = None
    hana_indexserver: Optional[int] = None
    enqueue: Optional[int] = None
    
    def get_all_ports(self) -> List[int]:
        """Get list of all configured ports."""
        ports = []
        for field in ['dispatcher', 'gateway', 'message_server', 'http', 
                      'https', 'hana_sql', 'hana_systemdb', 'hana_indexserver', 'enqueue']:
            port = getattr(self, field)
            if port is not None:
                ports.append(port)
        return ports
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary (excluding None values)."""
        result = {}
        for field in ['dispatcher', 'gateway', 'message_server', 'http', 
                      'https', 'hana_sql', 'hana_systemdb', 'hana_indexserver', 'enqueue']:
            port = getattr(self, field)
            if port is not None:
                result[field] = port
        return result


def calculate_instance_ports(
    instance_number: str,
    instance_type: Literal["ASCS", "ERS", "PAS", "AAS", "HDB", "J2EE", "Gateway", "WebDisp"]
) -> InstancePorts:
    """
    Calculate all relevant ports for an SAP instance based on its type.
    
    Args:
        instance_number: 2-digit instance number (00-99)
        instance_type: Type of SAP instance
        
    Returns:
        InstancePorts object with all calculated ports
        
    Example:
        >>> ports = calculate_instance_ports("00", "PAS")
        >>> ports.dispatcher
        3200
        >>> ports.gateway
        3300
        >>> ports.http
        8000
    """
    ports = InstancePorts(
        instance_number=instance_number,
        instance_type=instance_type
    )
    
    # ASCS (ABAP Central Services)
    if instance_type == "ASCS":
        ports.message_server = calculate_message_server_port(instance_number)
        ports.enqueue = calculate_enqueue_server_port(instance_number)
        ports.gateway = calculate_gateway_port(instance_number)
    
    # ERS (Enqueue Replication Server)
    elif instance_type == "ERS":
        ports.enqueue = calculate_enqueue_server_port(instance_number)
        ports.gateway = calculate_gateway_port(instance_number)
    
    # PAS (Primary Application Server)
    elif instance_type == "PAS":
        ports.dispatcher = calculate_dispatcher_port(instance_number)
        ports.gateway = calculate_gateway_port(instance_number)
        ports.message_server = calculate_message_server_port(instance_number)
        ports.http = calculate_http_port(instance_number)
        ports.https = calculate_https_port(instance_number)
    
    # AAS (Additional Application Server)
    elif instance_type == "AAS":
        ports.dispatcher = calculate_dispatcher_port(instance_number)
        ports.gateway = calculate_gateway_port(instance_number)
        ports.http = calculate_http_port(instance_number)
        ports.https = calculate_https_port(instance_number)
    
    # HDB (HANA Database)
    elif instance_type == "HDB":
        ports.hana_sql = calculate_hana_sql_port(instance_number)
        ports.hana_systemdb = calculate_hana_systemdb_port(instance_number)
        ports.hana_indexserver = calculate_hana_indexserver_port(instance_number)
        ports.http = calculate_http_port(instance_number)
        ports.https = calculate_https_port(instance_number)
    
    # J2EE (Java)
    elif instance_type == "J2EE":
        ports.dispatcher = calculate_dispatcher_port(instance_number)
        ports.gateway = calculate_gateway_port(instance_number)
        ports.http = calculate_http_port(instance_number)
        ports.https = calculate_https_port(instance_number)
    
    # Standalone Gateway
    elif instance_type == "Gateway":
        ports.gateway = calculate_gateway_port(instance_number)
    
    # Web Dispatcher
    elif instance_type == "WebDisp":
        ports.http = calculate_http_port(instance_number)
        ports.https = calculate_https_port(instance_number)
    
    logger.debug(
        "ports_calculated",
        instance=instance_number,
        type=instance_type,
        port_count=len(ports.get_all_ports())
    )
    
    return ports


# =============================================================================
# REVERSE CALCULATION (PORT → INSTANCE NUMBER)
# =============================================================================

def extract_instance_from_port(port: int, port_type: str) -> Optional[str]:
    """
    Reverse-calculate instance number from port.
    
    Args:
        port: Port number
        port_type: Type of port (dispatcher, gateway, message_server, etc.)
        
    Returns:
        2-digit instance number or None if invalid
        
    Example:
        >>> extract_instance_from_port(3200, "dispatcher")
        '00'
        >>> extract_instance_from_port(3310, "gateway")
        '10'
    """
    if port_type == "dispatcher":
        instance = port - 3200
    elif port_type == "gateway":
        instance = port - 3300
    elif port_type == "message_server":
        instance = port - 3600
    elif port_type == "http":
        instance = port - 8000
    elif port_type == "https":
        instance = port - 44300
    elif port_type == "hana_sql":
        instance = (port - 30015) // 100
    elif port_type == "hana_systemdb":
        instance = (port - 30013) // 100
    elif port_type == "hana_indexserver":
        instance = (port - 30003) // 100
    else:
        return None
    
    # Validate range
    if 0 <= instance <= 99:
        return f"{instance:02d}"
    return None


# =============================================================================
# PORT CONFLICT DETECTION
# =============================================================================

def detect_port_conflicts(instances: List[Dict]) -> List[Dict]:
    """
    Detect port conflicts between multiple SAP instances.
    
    Args:
        instances: List of dicts with 'instance_number' and 'instance_type'
        
    Returns:
        List of conflict descriptions
        
    Example:
        >>> instances = [
        ...     {"instance_number": "00", "instance_type": "PAS"},
        ...     {"instance_number": "00", "instance_type": "ASCS"}
        ... ]
        >>> conflicts = detect_port_conflicts(instances)
        >>> len(conflicts) > 0  # Will have conflicts
        True
    """
    port_map = {}  # port -> (instance_number, instance_type, port_name)
    conflicts = []
    
    for inst in instances:
        instance_number = inst["instance_number"]
        instance_type = inst["instance_type"]
        
        ports = calculate_instance_ports(instance_number, instance_type)
        
        for port_name, port_value in ports.to_dict().items():
            if port_value in port_map:
                # Conflict detected!
                existing = port_map[port_value]
                conflicts.append({
                    "port": port_value,
                    "instance_1": f"{existing[1]}{existing[0]}",
                    "port_name_1": existing[2],
                    "instance_2": f"{instance_type}{instance_number}",
                    "port_name_2": port_name,
                    "severity": "HIGH"
                })
            else:
                port_map[port_value] = (instance_number, instance_type, port_name)
    
    if conflicts:
        logger.warning(
            "port_conflicts_detected",
            conflict_count=len(conflicts)
        )
    
    return conflicts


# =============================================================================
# PORT VALIDATION
# =============================================================================

def validate_port_range(port: int) -> bool:
    """
    Validate if port is in valid range (1024-65535).
    
    Args:
        port: Port number to validate
        
    Returns:
        True if valid, False otherwise
    """
    return 1024 <= port <= 65535


def is_sap_standard_port(port: int) -> Optional[str]:
    """
    Check if port follows SAP standard formulas.
    
    Args:
        port: Port number
        
    Returns:
        Description of port type if standard, None otherwise
        
    Example:
        >>> is_sap_standard_port(3200)
        'Dispatcher (Instance 00)'
        >>> is_sap_standard_port(30015)
        'HANA SQL (Instance 00)'
    """
    # Dispatcher range
    if 3200 <= port <= 3299:
        instance = port - 3200
        return f"Dispatcher (Instance {instance:02d})"
    
    # Gateway range
    if 3300 <= port <= 3399:
        instance = port - 3300
        return f"Gateway (Instance {instance:02d})"
    
    # Message Server range
    if 3600 <= port <= 3699:
        instance = port - 3600
        return f"Message Server (Instance {instance:02d})"
    
    # HTTP range
    if 8000 <= port <= 8099:
        instance = port - 8000
        return f"HTTP (Instance {instance:02d})"
    
    # HTTPS range
    if 44300 <= port <= 44399:
        instance = port - 44300
        return f"HTTPS (Instance {instance:02d})"
    
    # HANA SQL range (multiples of 100 around 30015)
    if 30015 <= port <= 39915 and (port - 15) % 100 == 0:
        instance = (port - 30015) // 100
        return f"HANA SQL (Instance {instance:02d})"
    
    # HANA System DB range
    if 30013 <= port <= 39913 and (port - 13) % 100 == 0:
        instance = (port - 30013) // 100
        return f"HANA System DB (Instance {instance:02d})"
    
    return None


# =============================================================================
# BATCH OPERATIONS
# =============================================================================

def calculate_system_ports(instances: List[Dict]) -> Dict[str, InstancePorts]:
    """
    Calculate ports for all instances in a system.
    
    Args:
        instances: List of dicts with 'instance_number' and 'instance_type'
        
    Returns:
        Dict mapping instance ID to InstancePorts
        
    Example:
        >>> instances = [
        ...     {"instance_number": "01", "instance_type": "ASCS"},
        ...     {"instance_number": "00", "instance_type": "PAS"}
        ... ]
        >>> system_ports = calculate_system_ports(instances)
        >>> len(system_ports)
        2
    """
    result = {}
    
    for inst in instances:
        instance_number = inst["instance_number"]
        instance_type = inst["instance_type"]
        instance_id = f"{instance_type}{instance_number}"
        
        ports = calculate_instance_ports(instance_number, instance_type)
        result[instance_id] = ports
    
    logger.info(
        "system_ports_calculated",
        instance_count=len(instances),
        total_ports=sum(len(p.get_all_ports()) for p in result.values())
    )
    
    return result


def get_port_summary(instances: List[Dict]) -> str:
    """
    Generate human-readable port summary for instances.
    
    Args:
        instances: List of dicts with 'instance_number' and 'instance_type'
        
    Returns:
        Formatted string with port summary
    """
    system_ports = calculate_system_ports(instances)
    
    lines = ["SAP Instance Port Summary", "=" * 60]
    
    for instance_id, ports in system_ports.items():
        lines.append(f"\n{instance_id}:")
        for port_name, port_value in ports.to_dict().items():
            lines.append(f"  {port_name:20s}: {port_value}")
    
    lines.append("\n" + "=" * 60)
    
    return "\n".join(lines)


# End of SAP Port Calculator
