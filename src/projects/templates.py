"""
Veda 4.0 - SAP Ontology Base Template
Creates the foundational SAP knowledge graph template that gets cloned for new projects.

ARCHITECTURE:
- Defines all SAP node types (SAPSystem, SAPInstance, Host, Database, etc.)
- Defines all relationship types (RUNS_ON, DEPENDS_ON, USES_DATABASE, etc.)
- Creates a "template graph" named "sap_ontology_base"
- New projects clone this template to inherit the SAP structure

PURPOSE:
When you create a new project (e.g., client_a), it clones the sap_ontology_base
graph to get:
- Pre-defined node labels and properties
- Pre-defined relationship types
- SAP-specific constraints
- Best practice structure

USAGE:
    # Initialize template creator
    template_mgr = SAPTemplateManager(project_manager)
    
    # Create the base template (one-time setup)
    template_mgr.create_sap_ontology_base()
    
    # New projects automatically clone from this template
    project_manager.create_project("client_a", clone_from="sap_ontology_base")
"""

from typing import Dict, List, Optional
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class NodeTypeDefinition:
    """Defines a node type in the SAP ontology."""
    label: str                    # Node label (e.g., "SAPSystem")
    description: str              # Human-readable description
    required_properties: List[str]  # Must-have properties
    optional_properties: List[str]  # Nice-to-have properties
    example_cypher: str           # Example CREATE statement


@dataclass
class RelationshipTypeDefinition:
    """Defines a relationship type in the SAP ontology."""
    type: str                     # Relationship type (e.g., "RUNS_ON")
    description: str              # Human-readable description
    from_label: str               # Source node type
    to_label: str                 # Target node type
    properties: List[str]         # Relationship properties
    example_cypher: str           # Example CREATE statement


class SAPTemplateManager:
    """
    Manages the SAP ontology base template graph.
    
    This creates and maintains the "sap_ontology_base" graph that serves
    as the foundation for all project-specific SAP landscapes.
    """
    
    # SAP Node Type Definitions
    NODE_TYPES = [
        NodeTypeDefinition(
            label="SAPSystem",
            description="An SAP system identified by its SID (3-character system ID)",
            required_properties=["sid", "system_type", "landscape_tier"],
            optional_properties=[
                "description", "usage_type", "kernel_version", "kernel_patch",
                "basis_release", "client_numbers", "status", "created_at", "updated_at"
            ],
            example_cypher="""
            CREATE (:SAPSystem {
                sid: 'PRD',
                system_type: 'S/4HANA',
                landscape_tier: 'PRD',
                usage_type: 'ABAP',
                description: 'Production ERP System',
                kernel_version: '7.89',
                status: 'ACTIVE'
            })
            """
        ),
        
        NodeTypeDefinition(
            label="SAPInstance",
            description="An SAP instance (ASCS, PAS, AAS, HDB, etc.)",
            required_properties=["instance_type", "instance_number"],
            optional_properties=[
                "features", "start_priority", "status", "virtual_hostname",
                "process_count", "memory_gb", "created_at"
            ],
            example_cypher="""
            CREATE (:SAPInstance {
                instance_type: 'PAS',
                instance_number: '00',
                features: 'ABAP|GATEWAY|ICMAN',
                start_priority: 3,
                status: 'GREEN'
            })
            """
        ),
        
        NodeTypeDefinition(
            label="Host",
            description="Physical or virtual server running SAP instances",
            required_properties=["hostname"],
            optional_properties=[
                "fqdn", "os_type", "os_version", "ip_addresses", "cpu_cores",
                "ram_gb", "environment", "cloud_instance_type", "datacenter",
                "created_at", "updated_at"
            ],
            example_cypher="""
            CREATE (:Host {
                hostname: 'sap-prd-app01',
                fqdn: 'sap-prd-app01.company.com',
                os_type: 'SLES',
                os_version: '15 SP5',
                ip_addresses: ['10.0.1.50'],
                cpu_cores: 16,
                ram_gb: 128,
                environment: 'on-premise'
            })
            """
        ),
        
        NodeTypeDefinition(
            label="Database",
            description="Database system (HANA, Oracle, etc.)",
            required_properties=["db_type", "db_sid"],
            optional_properties=[
                "db_version", "tenant_name", "memory_allocated_gb",
                "backup_strategy", "port", "created_at", "updated_at"
            ],
            example_cypher="""
            CREATE (:Database {
                db_type: 'HANA',
                db_sid: 'HDB',
                db_version: '2.0 SPS07 Rev73',
                tenant_name: 'PRD',
                memory_allocated_gb: 256,
                backup_strategy: 'daily_full_hourly_log'
            })
            """
        ),
        
        NodeTypeDefinition(
            label="Client",
            description="SAP client/mandant within a system",
            required_properties=["client_number", "description"],
            optional_properties=[
                "role", "is_open", "is_production", "created_at"
            ],
            example_cypher="""
            CREATE (:Client {
                client_number: '100',
                description: 'Production Client',
                role: 'Production',
                is_open: false
            })
            """
        ),
        
        NodeTypeDefinition(
            label="TransportRoute",
            description="Transport route between systems",
            required_properties=["route_type"],
            optional_properties=["description", "created_at"],
            example_cypher="""
            CREATE (:TransportRoute {
                route_type: 'Consolidation',
                description: 'DEV to QAS consolidation'
            })
            """
        ),
        
        NodeTypeDefinition(
            label="NetworkSegment",
            description="Network subnet/VLAN",
            required_properties=["subnet"],
            optional_properties=["vlan", "zone", "description", "firewall_rules"],
            example_cypher="""
            CREATE (:NetworkSegment {
                subnet: '10.0.1.0/24',
                vlan: 'VLAN100',
                zone: 'APP',
                description: 'Application tier network'
            })
            """
        ),
        
        NodeTypeDefinition(
            label="RFCDestination",
            description="RFC connection configuration",
            required_properties=["rfc_name", "connection_type"],
            optional_properties=[
                "target_client", "is_trusted", "load_balancing",
                "description", "created_at"
            ],
            example_cypher="""
            CREATE (:RFCDestination {
                rfc_name: 'PRD_TO_BW_RFC',
                connection_type: '3',
                target_client: '100',
                is_trusted: true
            })
            """
        ),
    ]
    
    # SAP Relationship Type Definitions
    RELATIONSHIP_TYPES = [
        RelationshipTypeDefinition(
            type="HAS_INSTANCE",
            description="System contains instance",
            from_label="SAPSystem",
            to_label="SAPInstance",
            properties=["created_at"],
            example_cypher="""
            MATCH (s:SAPSystem {sid: 'PRD'}), (i:SAPInstance {instance_number: '00'})
            CREATE (s)-[:HAS_INSTANCE {created_at: '2024-01-01'}]->(i)
            """
        ),
        
        RelationshipTypeDefinition(
            type="RUNS_ON",
            description="Instance runs on host",
            from_label="SAPInstance",
            to_label="Host",
            properties=["valid_from", "valid_to", "created_at"],
            example_cypher="""
            MATCH (i:SAPInstance), (h:Host {hostname: 'sap-app01'})
            CREATE (i)-[:RUNS_ON {valid_from: '2024-01-01', valid_to: null}]->(h)
            """
        ),
        
        RelationshipTypeDefinition(
            type="USES_DATABASE",
            description="System uses database",
            from_label="SAPSystem",
            to_label="Database",
            properties=["connection_type", "schema_owner", "created_at"],
            example_cypher="""
            MATCH (s:SAPSystem {sid: 'PRD'}), (d:Database {db_type: 'HANA'})
            CREATE (s)-[:USES_DATABASE {connection_type: 'JDBC'}]->(d)
            """
        ),
        
        RelationshipTypeDefinition(
            type="HOSTED_ON",
            description="Database hosted on server",
            from_label="Database",
            to_label="Host",
            properties=["valid_from", "valid_to"],
            example_cypher="""
            MATCH (d:Database), (h:Host {hostname: 'sap-db01'})
            CREATE (d)-[:HOSTED_ON {valid_from: '2024-01-01'}]->(h)
            """
        ),
        
        RelationshipTypeDefinition(
            type="HAS_CLIENT",
            description="System has client/mandant",
            from_label="SAPSystem",
            to_label="Client",
            properties=["created_at"],
            example_cypher="""
            MATCH (s:SAPSystem {sid: 'PRD'}), (c:Client {client_number: '100'})
            CREATE (s)-[:HAS_CLIENT]->(c)
            """
        ),
        
        RelationshipTypeDefinition(
            type="TRANSPORTS_TO",
            description="Transport route between systems",
            from_label="SAPSystem",
            to_label="SAPSystem",
            properties=["route_type", "transport_layer", "created_at"],
            example_cypher="""
            MATCH (dev:SAPSystem {sid: 'DEV'}), (qas:SAPSystem {sid: 'QAS'})
            CREATE (dev)-[:TRANSPORTS_TO {route_type: 'Consolidation'}]->(qas)
            """
        ),
        
        RelationshipTypeDefinition(
            type="DEPENDS_ON",
            description="Instance dependency (startup order)",
            from_label="SAPInstance",
            to_label="SAPInstance",
            properties=["dependency_type", "is_critical"],
            example_cypher="""
            MATCH (pas:SAPInstance {instance_type: 'PAS'}),
                  (ascs:SAPInstance {instance_type: 'ASCS'})
            CREATE (pas)-[:DEPENDS_ON {dependency_type: 'enqueue', is_critical: true}]->(ascs)
            """
        ),
        
        RelationshipTypeDefinition(
            type="FAILOVER_FOR",
            description="Failover/high-availability relationship",
            from_label="SAPInstance",
            to_label="SAPInstance",
            properties=["failover_mode", "sync_mode"],
            example_cypher="""
            MATCH (ers:SAPInstance {instance_type: 'ERS'}),
                  (ascs:SAPInstance {instance_type: 'ASCS'})
            CREATE (ers)-[:FAILOVER_FOR {failover_mode: 'ENSA2'}]->(ascs)
            """
        ),
        
        RelationshipTypeDefinition(
            type="BELONGS_TO_NETWORK",
            description="Host belongs to network segment",
            from_label="Host",
            to_label="NetworkSegment",
            properties=["created_at"],
            example_cypher="""
            MATCH (h:Host), (n:NetworkSegment {subnet: '10.0.1.0/24'})
            CREATE (h)-[:BELONGS_TO_NETWORK]->(n)
            """
        ),
        
        RelationshipTypeDefinition(
            type="CONNECTS_VIA",
            description="System uses RFC destination",
            from_label="SAPSystem",
            to_label="RFCDestination",
            properties=["created_at"],
            example_cypher="""
            MATCH (s:SAPSystem {sid: 'PRD'}), (r:RFCDestination {rfc_name: 'PRD_TO_BW'})
            CREATE (s)-[:CONNECTS_VIA]->(r)
            """
        ),
        
        RelationshipTypeDefinition(
            type="TARGETS",
            description="RFC destination targets system",
            from_label="RFCDestination",
            to_label="SAPSystem",
            properties=["created_at"],
            example_cypher="""
            MATCH (r:RFCDestination), (t:SAPSystem {sid: 'BW'})
            CREATE (r)-[:TARGETS]->(t)
            """
        ),
    ]
    
    def __init__(self, project_manager):
        """
        Initialize SAP template manager.
        
        Args:
            project_manager: ProjectContextManager instance
        """
        self.project_manager = project_manager
        logger.info("sap_template_manager_initialized")
    
    def create_sap_ontology_base(self) -> bool:
        """
        Create the SAP ontology base template graph.
        
        This is a one-time setup that creates the "sap_ontology_base" graph
        with documentation nodes explaining the SAP structure.
        
        Returns:
            True if created successfully, False if already exists
            
        Example:
            >>> template_mgr = SAPTemplateManager(project_manager)
            >>> template_mgr.create_sap_ontology_base()
            True
        """
        template_name = "sap_ontology_base"
        
        # Check if template already exists
        existing_graphs = self.project_manager.db.list_graphs()
        if template_name in existing_graphs:
            logger.warning(
                "sap_ontology_base_exists",
                message="Template already exists, skipping creation"
            )
            return False
        
        logger.info("creating_sap_ontology_base")
        
        # Create the template graph
        template_graph = self.project_manager.db.select_graph(template_name)
        
        # Create documentation node
        doc_cypher = """
        CREATE (:TemplateMetadata {
            name: 'SAP Ontology Base',
            version: '4.0',
            created_at: 'February 2026',
            description: 'Base SAP landscape ontology for Veda 4.0',
            node_types: $node_types,
            relationship_types: $relationship_types
        })
        """
        
        template_graph.query(doc_cypher, {
            "node_types": [nt.label for nt in self.NODE_TYPES],
            "relationship_types": [rt.type for rt in self.RELATIONSHIP_TYPES]
        })
        
        # Create example nodes (one of each type for reference)
        self._create_example_nodes(template_graph)
        
        # Create example relationships
        self._create_example_relationships(template_graph)
        
        logger.info(
            "sap_ontology_base_created",
            node_types=len(self.NODE_TYPES),
            relationship_types=len(self.RELATIONSHIP_TYPES)
        )
        
        return True
    
    def _create_example_nodes(self, graph):
        """Create example nodes of each type."""
        
        # Example SAP System
        graph.query("""
        CREATE (:SAPSystem {
            sid: 'EXAMPLE',
            system_type: 'S/4HANA',
            landscape_tier: 'TEMPLATE',
            usage_type: 'ABAP',
            description: 'Example system for reference',
            status: 'TEMPLATE'
        })
        """)
        
        # Example Host
        graph.query("""
        CREATE (:Host {
            hostname: 'example-host',
            os_type: 'SLES',
            os_version: '15 SP5',
            environment: 'template'
        })
        """)
        
        # Example Database
        graph.query("""
        CREATE (:Database {
            db_type: 'HANA',
            db_sid: 'HDB',
            db_version: '2.0 SPS07'
        })
        """)
        
        logger.debug("example_nodes_created")
    
    def _create_example_relationships(self, graph):
        """Create example relationships between nodes."""
        
        # Example: System uses Database
        graph.query("""
        MATCH (s:SAPSystem {sid: 'EXAMPLE'}), (d:Database {db_type: 'HANA'})
        CREATE (s)-[:USES_DATABASE {connection_type: 'JDBC'}]->(d)
        """)
        
        # Example: Database hosted on Host
        graph.query("""
        MATCH (d:Database {db_type: 'HANA'}), (h:Host {hostname: 'example-host'})
        CREATE (d)-[:HOSTED_ON]->(h)
        """)
        
        logger.debug("example_relationships_created")
    
    def get_node_type_documentation(self) -> Dict[str, NodeTypeDefinition]:
        """
        Get documentation for all SAP node types.
        
        Returns:
            Dict mapping label to NodeTypeDefinition
        """
        return {nt.label: nt for nt in self.NODE_TYPES}
    
    def get_relationship_type_documentation(self) -> Dict[str, RelationshipTypeDefinition]:
        """
        Get documentation for all SAP relationship types.
        
        Returns:
            Dict mapping type to RelationshipTypeDefinition
        """
        return {rt.type: rt for rt in self.RELATIONSHIP_TYPES}
    
    def print_ontology_reference(self):
        """
        Print a human-readable reference guide for the SAP ontology.
        
        Useful for documentation and onboarding.
        """
        print("=" * 70)
        print("SAP ONTOLOGY REFERENCE - VEDA 4.0")
        print("=" * 70)
        
        print("\n📦 NODE TYPES:")
        print("-" * 70)
        for nt in self.NODE_TYPES:
            print(f"\n{nt.label}")
            print(f"  Description: {nt.description}")
            print(f"  Required: {', '.join(nt.required_properties)}")
            if nt.optional_properties:
                print(f"  Optional: {', '.join(nt.optional_properties[:5])}...")
        
        print("\n\n🔗 RELATIONSHIP TYPES:")
        print("-" * 70)
        for rt in self.RELATIONSHIP_TYPES:
            print(f"\n{rt.type}")
            print(f"  Description: {rt.description}")
            print(f"  Pattern: ({rt.from_label})-[:{rt.type}]->({rt.to_label})")
            if rt.properties:
                print(f"  Properties: {', '.join(rt.properties)}")
        
        print("\n" + "=" * 70)


# End of SAPTemplateManager implementation
