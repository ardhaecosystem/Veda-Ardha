"""
Veda 4.0 - SAP Ontology Models
Pydantic models for all SAP landscape entity types.

These models provide:
- Type safety for SAP entities
- Validation for SID formats, instance numbers, etc.
- Helper methods for common operations
- Serialization for storage in FalkorDB

Matches the node types defined in templates.py with full Python typing.
"""

from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, computed_field
import re

import structlog

logger = structlog.get_logger()


# =============================================================================
# SAP SYSTEM ENTITIES
# =============================================================================

class SAPSystem(BaseModel):
    """
    An SAP system identified by its SID (System ID).
    
    Examples:
    - Production ERP: SID='PRD', system_type='S/4HANA', tier='PRD'
    - Development: SID='DEV', system_type='ECC', tier='DEV'
    - BW System: SID='BWP', system_type='BW/4HANA', tier='PRD'
    """
    
    # Required fields
    sid: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3-character SAP System ID (e.g., PRD, QAS, DEV)"
    )
    system_type: str = Field(
        ...,
        description="SAP product type (S/4HANA, ECC, BW/4HANA, Solution Manager, etc.)"
    )
    landscape_tier: Literal["PRD", "QAS", "DEV", "SBX", "TRN"] = Field(
        ...,
        description="Landscape tier: PRD (Production), QAS (Quality), DEV (Development), SBX (Sandbox), TRN (Training)"
    )
    
    # Optional fields
    usage_type: Optional[Literal["ABAP", "JAVA", "DUAL_STACK"]] = Field(
        default="ABAP",
        description="Stack type: ABAP (most common), JAVA, or DUAL_STACK"
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description (e.g., 'Production ERP System')"
    )
    kernel_version: Optional[str] = Field(
        default=None,
        description="SAP Kernel version (e.g., '7.89')"
    )
    kernel_patch: Optional[int] = Field(
        default=None,
        description="Kernel patch level"
    )
    basis_release: Optional[str] = Field(
        default=None,
        description="SAP Basis release (e.g., '750', '753')"
    )
    client_numbers: Optional[List[str]] = Field(
        default_factory=list,
        description="List of client numbers (mandants) in this system"
    )
    status: Optional[Literal["ACTIVE", "INACTIVE", "MAINTENANCE", "DECOMMISSIONED"]] = Field(
        default="ACTIVE",
        description="Current operational status"
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="When this system was added to Veda"
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="When this system was last updated"
    )
    
    @field_validator('sid')
    @classmethod
    def validate_sid(cls, v: str) -> str:
        """
        Validate SID format:
        - Must be exactly 3 characters
        - Must start with a letter
        - Can only contain alphanumeric characters
        - Cannot be reserved words
        """
        v = v.upper()
        
        # Check length
        if len(v) != 3:
            raise ValueError(f"SID must be exactly 3 characters, got '{v}'")
        
        # Must start with letter
        if not v[0].isalpha():
            raise ValueError(f"SID must start with a letter, got '{v}'")
        
        # Only alphanumeric
        if not v.isalnum():
            raise ValueError(f"SID must be alphanumeric, got '{v}'")
        
        # Reserved words (SAP and common system IDs)
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
        
        if v in reserved:
            raise ValueError(f"SID '{v}' is a reserved word and cannot be used")
        
        return v
    
    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if this is a production system."""
        return self.landscape_tier == "PRD"
    
    def __str__(self) -> str:
        return f"{self.sid} ({self.system_type} - {self.landscape_tier})"


class SAPInstance(BaseModel):
    """
    An SAP instance running on a host.
    
    Instance types:
    - ASCS: ABAP Central Services (Enqueue + Message Server)
    - ERS: Enqueue Replication Server (ASCS failover)
    - PAS: Primary Application Server
    - AAS: Additional Application Server
    - HDB: HANA Database instance
    - J2EE: Java instance
    - Gateway: SAP Gateway (standalone)
    - WebDisp: Web Dispatcher
    """
    
    # Required fields
    instance_type: Literal[
        "ASCS", "ERS", "PAS", "AAS", "HDB", 
        "J2EE", "Gateway", "WebDisp", "SCS", "Central"
    ] = Field(
        ...,
        description="Type of SAP instance"
    )
    instance_number: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="2-digit instance number (00-99)"
    )
    
    # Optional fields
    features: Optional[str] = Field(
        default=None,
        description="Pipe-separated features (e.g., 'ABAP|GATEWAY|ICMAN')"
    )
    start_priority: Optional[int] = Field(
        default=None,
        ge=1,
        le=99,
        description="Startup priority (1=first, higher=later)"
    )
    status: Optional[Literal["GREEN", "YELLOW", "RED", "GRAY"]] = Field(
        default="GREEN",
        description="Current instance status from sapcontrol"
    )
    virtual_hostname: Optional[str] = Field(
        default=None,
        description="Virtual hostname for HA setups"
    )
    process_count: Optional[int] = Field(
        default=None,
        description="Number of work processes configured"
    )
    memory_gb: Optional[int] = Field(
        default=None,
        description="Memory allocation in GB"
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    
    @field_validator('instance_number')
    @classmethod
    def validate_instance_number(cls, v: str) -> str:
        """
        Validate instance number format:
        - Must be exactly 2 digits
        - Range: 00-99
        """
        if not v.isdigit():
            raise ValueError(f"Instance number must be numeric, got '{v}'")
        
        if len(v) != 2:
            raise ValueError(f"Instance number must be 2 digits, got '{v}'")
        
        num = int(v)
        if num < 0 or num > 99:
            raise ValueError(f"Instance number must be 00-99, got '{v}'")
        
        return v
    
    @computed_field
    @property
    def is_central_services(self) -> bool:
        """Check if this is a central services instance (ASCS/SCS)."""
        return self.instance_type in ["ASCS", "SCS", "ERS"]
    
    @computed_field
    @property
    def is_application_server(self) -> bool:
        """Check if this is an application server (PAS/AAS)."""
        return self.instance_type in ["PAS", "AAS", "Central"]
    
    def __str__(self) -> str:
        return f"{self.instance_type}{self.instance_number}"


class Host(BaseModel):
    """
    Physical or virtual server hosting SAP instances.
    """
    
    # Required fields
    hostname: str = Field(
        ...,
        min_length=1,
        description="Hostname (short name, not FQDN)"
    )
    
    # Optional fields
    fqdn: Optional[str] = Field(
        default=None,
        description="Fully qualified domain name"
    )
    os_type: Optional[Literal["SLES", "RHEL", "Windows", "AIX", "Solaris", "HP-UX"]] = Field(
        default=None,
        description="Operating system type"
    )
    os_version: Optional[str] = Field(
        default=None,
        description="OS version (e.g., 'SLES 15 SP5', 'RHEL 8.6')"
    )
    ip_addresses: Optional[List[str]] = Field(
        default_factory=list,
        description="List of IP addresses (can have multiple for HA)"
    )
    cpu_cores: Optional[int] = Field(
        default=None,
        description="Number of CPU cores"
    )
    ram_gb: Optional[int] = Field(
        default=None,
        description="Total RAM in GB"
    )
    environment: Optional[Literal["on-premise", "azure", "aws", "gcp", "hybrid"]] = Field(
        default="on-premise",
        description="Hosting environment"
    )
    cloud_instance_type: Optional[str] = Field(
        default=None,
        description="Cloud instance type (e.g., 'Standard_E32s_v3' for Azure)"
    )
    datacenter: Optional[str] = Field(
        default=None,
        description="Physical datacenter or cloud region"
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    
    @field_validator('hostname')
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        """Validate hostname format (RFC 1123)."""
        # Allow alphanumeric, hyphens, but not starting/ending with hyphen
        pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
        if not re.match(pattern, v):
            raise ValueError(
                f"Invalid hostname '{v}'. Must be alphanumeric with hyphens, "
                "1-63 characters, not start/end with hyphen"
            )
        return v.lower()
    
    def __str__(self) -> str:
        return self.hostname


class Database(BaseModel):
    """
    Database system (HANA, Oracle, DB2, MaxDB, etc.).
    """
    
    # Required fields
    db_type: Literal["HANA", "Oracle", "DB2", "MaxDB", "ASE", "MSSQL"] = Field(
        ...,
        description="Database type"
    )
    db_sid: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Database SID (usually same as SAP SID, but can differ)"
    )
    
    # Optional fields
    db_version: Optional[str] = Field(
        default=None,
        description="Database version (e.g., 'HANA 2.0 SPS07 Rev73', 'Oracle 19c')"
    )
    tenant_name: Optional[str] = Field(
        default=None,
        description="HANA tenant name (for MDC/multi-tenant)"
    )
    memory_allocated_gb: Optional[int] = Field(
        default=None,
        description="Memory allocated to database in GB"
    )
    backup_strategy: Optional[str] = Field(
        default=None,
        description="Backup strategy description"
    )
    port: Optional[int] = Field(
        default=None,
        description="Database port (e.g., 30015 for HANA)"
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    
    @field_validator('db_sid')
    @classmethod
    def validate_db_sid(cls, v: str) -> str:
        """Validate DB SID (same rules as SAP SID)."""
        v = v.upper()
        
        if len(v) != 3:
            raise ValueError(f"DB SID must be exactly 3 characters, got '{v}'")
        
        if not v[0].isalpha():
            raise ValueError(f"DB SID must start with a letter, got '{v}'")
        
        if not v.isalnum():
            raise ValueError(f"DB SID must be alphanumeric, got '{v}'")
        
        return v
    
    @computed_field
    @property
    def is_hana(self) -> bool:
        """Check if this is SAP HANA."""
        return self.db_type == "HANA"
    
    def __str__(self) -> str:
        return f"{self.db_type}/{self.db_sid}"


class Client(BaseModel):
    """
    SAP client/mandant within a system.
    
    Common clients:
    - 000: SAP master client
    - 001: SAP template client
    - 066: EarlyWatch client
    - 100+: Customer clients (production)
    - 200+: Customer clients (quality)
    - 300+: Customer clients (development)
    """
    
    # Required fields
    client_number: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3-digit client number (000-999)"
    )
    description: str = Field(
        ...,
        description="Client description"
    )
    
    # Optional fields
    role: Optional[Literal[
        "Production", "Quality", "Development", 
        "Training", "Sandbox", "Template", "Master"
    ]] = Field(
        default=None,
        description="Client role/purpose"
    )
    is_open: Optional[bool] = Field(
        default=False,
        description="Whether client allows changes (usually false for production)"
    )
    is_production: Optional[bool] = Field(
        default=False,
        description="Whether this is a production client"
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    
    @field_validator('client_number')
    @classmethod
    def validate_client_number(cls, v: str) -> str:
        """Validate client number: 3 digits, 000-999."""
        if not v.isdigit():
            raise ValueError(f"Client number must be numeric, got '{v}'")
        
        if len(v) != 3:
            raise ValueError(f"Client number must be 3 digits, got '{v}'")
        
        num = int(v)
        if num < 0 or num > 999:
            raise ValueError(f"Client number must be 000-999, got '{v}'")
        
        return v
    
    def __str__(self) -> str:
        return f"Client {self.client_number} ({self.description})"


# =============================================================================
# INFRASTRUCTURE ENTITIES
# =============================================================================

class NetworkSegment(BaseModel):
    """
    Network subnet/VLAN for SAP landscape.
    """
    
    # Required fields
    subnet: str = Field(
        ...,
        description="Subnet in CIDR notation (e.g., '10.0.1.0/24')"
    )
    
    # Optional fields
    vlan: Optional[str] = Field(
        default=None,
        description="VLAN identifier (e.g., 'VLAN100')"
    )
    zone: Optional[Literal["APP", "DB", "WEB", "DMZ", "MGMT"]] = Field(
        default=None,
        description="Network zone/tier"
    )
    description: Optional[str] = Field(
        default=None,
        description="Network segment description"
    )
    firewall_rules: Optional[List[str]] = Field(
        default_factory=list,
        description="Applied firewall rules"
    )
    
    @field_validator('subnet')
    @classmethod
    def validate_subnet(cls, v: str) -> str:
        """Basic CIDR validation."""
        pattern = r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$'
        if not re.match(pattern, v):
            raise ValueError(f"Invalid CIDR notation: '{v}'")
        return v
    
    def __str__(self) -> str:
        return f"{self.subnet} ({self.zone or 'Unknown zone'})"


class TransportRoute(BaseModel):
    """
    Transport route between SAP systems.
    
    Route types:
    - Consolidation: DEV → QAS
    - Delivery: QAS → PRD
    - Transport of Copies: Direct copy (not recommended)
    """
    
    # Required fields
    route_type: Literal["Consolidation", "Delivery", "Transport_of_Copies"] = Field(
        ...,
        description="Type of transport route"
    )
    
    # Optional fields
    description: Optional[str] = Field(
        default=None,
        description="Route description"
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    
    def __str__(self) -> str:
        return f"{self.route_type} route"


class RFCDestination(BaseModel):
    """
    RFC (Remote Function Call) connection configuration.
    
    Connection types:
    - Type 3: ABAP connection
    - Type T: TCP/IP connection
    - Type H: HTTP connection
    """
    
    # Required fields
    rfc_name: str = Field(
        ...,
        description="RFC destination name (e.g., 'PRD_TO_BW_RFC')"
    )
    connection_type: Literal["3", "T", "H", "G", "L"] = Field(
        ...,
        description="RFC connection type (3=ABAP, T=TCP/IP, H=HTTP, G=External, L=Logical)"
    )
    
    # Optional fields
    target_client: Optional[str] = Field(
        default=None,
        description="Target client number (for Type 3)"
    )
    is_trusted: Optional[bool] = Field(
        default=False,
        description="Whether connection is trusted (no password required)"
    )
    load_balancing: Optional[bool] = Field(
        default=False,
        description="Whether load balancing is enabled"
    )
    description: Optional[str] = Field(
        default=None,
        description="RFC destination description"
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now
    )
    
    def __str__(self) -> str:
        return f"RFC {self.rfc_name} (Type {self.connection_type})"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_sap_system_from_dict(data: dict) -> SAPSystem:
    """
    Create SAPSystem from dictionary with validation.
    
    Useful for parsing user input or API payloads.
    """
    try:
        return SAPSystem(**data)
    except Exception as e:
        logger.error("sap_system_validation_failed", error=str(e), data=data)
        raise


def create_instance_from_dict(data: dict) -> SAPInstance:
    """Create SAPInstance from dictionary with validation."""
    try:
        return SAPInstance(**data)
    except Exception as e:
        logger.error("sap_instance_validation_failed", error=str(e), data=data)
        raise


def validate_landscape_data(systems: List[dict]) -> tuple[List[SAPSystem], List[str]]:
    """
    Validate a list of SAP systems and return valid ones + error messages.
    
    Args:
        systems: List of system dictionaries
        
    Returns:
        Tuple of (valid_systems, error_messages)
        
    Example:
        >>> systems = [
        ...     {"sid": "PRD", "system_type": "S/4HANA", "landscape_tier": "PRD"},
        ...     {"sid": "INVALID!", "system_type": "ECC", "landscape_tier": "DEV"}
        ... ]
        >>> valid, errors = validate_landscape_data(systems)
        >>> len(valid)  # 1
        >>> len(errors)  # 1
    """
    valid_systems = []
    errors = []
    
    for i, system_data in enumerate(systems):
        try:
            system = SAPSystem(**system_data)
            valid_systems.append(system)
        except Exception as e:
            errors.append(f"System {i+1}: {str(e)}")
    
    return valid_systems, errors


# End of SAP Ontology Models
