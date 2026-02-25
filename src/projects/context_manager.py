"""
Veda 4.0 - Project Context Manager with RBAC (Phase 1 + Phase 2)
Multi-project isolation system using FalkorDB's native multi-graph support.

ARCHITECTURE:
- Each project gets its own named FalkorDB graph (e.g., "project_client_a")
- Physical isolation: Separate sparse adjacency matrices = zero cross-contamination
- Lightweight mounting: Graph selection is a pointer operation (<1ms)
- Backward compatible: Defaults to "personal_memory" and "work_memory" if no project
- RBAC integration: Optional access control with admin/editor/viewer roles (Phase 2)

USAGE (Phase 1 - No RBAC):
    # Initialize without access control (backward compatible)
    manager = ProjectContextManager(
        falkordb_host="localhost",
        falkordb_port=6379,
        falkordb_password="your-password"
    )

    # Mount a project (no permission check)
    context = manager.mount("client_a")

USAGE (Phase 2 - With RBAC):
    # Initialize with access control
    from src.projects.access_control import AccessControl
    
    access_control = AccessControl(redis_url="redis://localhost:6380")
    await access_control.initialize()
    
    manager = ProjectContextManager(
        falkordb_host="localhost",
        falkordb_port=6379,
        falkordb_password="your-password",
        access_control=access_control  # NEW!
    )
    
    # Mount with permission check
    context = manager.mount("client_a", user_id="user123")  # NEW!

SAFETY:
- RuntimeError if attempting to query without mounted context
- Automatic validation of project names (alphanumeric + underscore only)
- Connection pooling for performance
- Graceful error handling with detailed logging
- RBAC: Permission checks for mount/create/delete (Phase 2)
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, TYPE_CHECKING
from datetime import datetime

import structlog

# Conditional import for type checking (avoid circular imports)
if TYPE_CHECKING:
    from .access_control import AccessControl

# FalkorDB imports - using the EXACT same pattern from your memory_manager.py
try:
    from falkordb import FalkorDB
except ImportError:
    raise ImportError(
        "FalkorDB not installed. Install with: uv add 'graphiti-core[falkordb]'"
    )

logger = structlog.get_logger()


@dataclass
class ProjectContext:
    """
    Represents an active project context.

    This is a lightweight wrapper around a FalkorDB graph handle.
    Think of it as a "mental model" that Veda switches between.
    """
    project_id: str                    # User-friendly name (e.g., "client_a")
    graph_name: str                    # FalkorDB graph name (e.g., "project_client_a")
    graph: object                      # FalkorDB Graph object (lightweight pointer)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)  # Custom metadata (optional)

    def __repr__(self):
        return f"ProjectContext(project_id='{self.project_id}', graph='{self.graph_name}')"


class ProjectContextManager:
    """
    Manages multi-project isolation with strict context enforcement.

    ISOLATION GUARANTEES:
    - FalkorDB native multi-graph = physical separation
    - No cross-graph queries possible (enforced at database level)
    - Application-level guards prevent accidental cross-contamination
    - RBAC: Role-based access control for mount/create/delete (Phase 2)

    PERFORMANCE:
    - Graph mounting: <1ms (pointer operation)
    - Graph caching: Reuses connections for frequently accessed projects
    - Connection pooling: Single FalkorDB client for all graphs
    """

    # Valid project ID pattern: alphanumeric + underscore only
    # Examples: "client_a", "sap_prod", "customer_123"
    PROJECT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')

    # Reserved names that cannot be used for projects
    RESERVED_NAMES = {
        'personal_memory',      # Veda 3.0 personal graph
        'work_memory',          # Veda 3.0 work graph
        'sap_ontology_base',    # SAP knowledge base template
        'system',               # System metadata
        'admin',                # Administrative functions
    }

    def __init__(
        self,
        falkordb_host: str = "localhost",
        falkordb_port: int = 6379,
        falkordb_password: Optional[str] = None,
        access_control: Optional['AccessControl'] = None,  # NEW: Phase 2
    ):
        """
        Initialize the project context manager.

        Args:
            falkordb_host: FalkorDB server hostname
            falkordb_port: FalkorDB server port (default: 6379)
            falkordb_password: FalkorDB password (from .env)
            access_control: Optional AccessControl instance for RBAC (Phase 2)

        Raises:
            ConnectionError: If cannot connect to FalkorDB
        """
        self.host = falkordb_host
        self.port = falkordb_port
        self.password = falkordb_password
        self.access_control = access_control  # NEW: Phase 2

        # Initialize FalkorDB client (connection pool)
        try:
            self.db = FalkorDB(
                host=self.host,
                port=self.port,
                password=self.password
            )
            logger.info(
                "project_context_manager_initialized",
                host=self.host,
                port=self.port,
                rbac_enabled=bool(self.access_control)  # NEW: Phase 2
            )
        except Exception as e:
            logger.error(
                "falkordb_connection_failed",
                host=self.host,
                port=self.port,
                error=str(e)
            )
            raise ConnectionError(f"Cannot connect to FalkorDB: {e}")

        # Currently mounted project context
        self._active: Optional[ProjectContext] = None

        # Graph cache: {graph_name: Graph object}
        # Reuses graph handles for performance
        self._cache: Dict[str, object] = {}

        logger.info(
            "project_context_manager_ready",
            rbac_mode="enabled" if self.access_control else "disabled"
        )

    def validate_project_id(self, project_id: str) -> bool:
        """
        Validate project ID format.

        Rules:
        - Alphanumeric + underscore only
        - Not in reserved names list
        - Not empty

        Args:
            project_id: Project identifier to validate

        Returns:
            True if valid, raises ValueError if invalid
        """
        if not project_id:
            raise ValueError("Project ID cannot be empty")

        if project_id in self.RESERVED_NAMES:
            raise ValueError(
                f"Project ID '{project_id}' is reserved. "
                f"Reserved names: {self.RESERVED_NAMES}"
            )

        if not self.PROJECT_ID_PATTERN.match(project_id):
            raise ValueError(
                f"Invalid project ID '{project_id}'. "
                f"Only alphanumeric characters and underscores allowed."
            )

        return True

    async def _check_access_async(
        self,
        user_id: str,
        project_id: str,
        operation: str = "read"
    ) -> bool:
        """
        Check if user has access to project (async version for RBAC).
        
        Args:
            user_id: User identifier
            project_id: Project identifier
            operation: Operation type (read/write/admin)
            
        Returns:
            True if has access
            
        Raises:
            PermissionError: If access denied
        """
        if not self.access_control:
            # No RBAC - allow all (backward compatible)
            return True
        
        # Check permissions based on operation
        if operation == "admin":
            # Admin operations (create/delete)
            if not await self.access_control.can_manage_users(user_id, project_id):
                raise PermissionError(
                    f"User '{user_id}' lacks admin permissions for project '{project_id}'"
                )
        elif operation == "write":
            if not await self.access_control.can_write(user_id, project_id):
                raise PermissionError(
                    f"User '{user_id}' lacks write permissions for project '{project_id}'"
                )
        else:  # read
            if not await self.access_control.can_access(user_id, project_id):
                raise PermissionError(
                    f"User '{user_id}' does not have access to project '{project_id}'"
                )
        
        return True

    def _check_access_sync(
        self,
        user_id: Optional[str],
        project_id: str
    ) -> bool:
        """
        Synchronous access check for mount() method.
        Uses cached permissions for fast path.
        
        Args:
            user_id: User identifier (None for backward compatibility)
            project_id: Project identifier
            
        Returns:
            True if has access
            
        Raises:
            PermissionError: If access denied
        """
        if not user_id or not self.access_control:
            # No RBAC or no user_id - allow (backward compatible)
            return True
        
        # Try synchronous cache check (fast path)
        if self.access_control.can_read(user_id, project_id):
            return True
        
        # Cache miss - user needs async check or doesn't have access
        raise PermissionError(
            f"User '{user_id}' does not have access to project '{project_id}'. "
            f"Grant access first: access_control.grant_access('{user_id}', '{project_id}', 'viewer')"
        )

    def mount(
        self,
        project_id: str,
        metadata: Optional[Dict] = None,
        user_id: Optional[str] = None  # NEW: Phase 2
    ) -> ProjectContext:
        """
        Mount a project context (switch Veda's "mental model").

        This is how you tell Veda: "You're now working on Client A's landscape."
        All subsequent queries will be scoped to this project's graph.

        Args:
            project_id: Project identifier (e.g., "client_a")
            metadata: Optional metadata dict (e.g., {"client_name": "ACME Corp"})
            user_id: User identifier for RBAC (optional, Phase 2)

        Returns:
            ProjectContext object representing the mounted project

        Raises:
            ValueError: If project_id is invalid
            RuntimeError: If project doesn't exist
            PermissionError: If user lacks access (Phase 2)

        Example (Phase 1):
            >>> manager.mount("client_a")
            
        Example (Phase 2):
            >>> manager.mount("client_a", user_id="user123")
        """
        # Validate project ID format
        self.validate_project_id(project_id)

        # Phase 2: Check permissions
        if user_id:
            self._check_access_sync(user_id, project_id)
            logger.debug(
                "mount_permission_granted",
                user_id=user_id,
                project_id=project_id
            )

        # Construct graph name (consistent naming: "project_{id}")
        graph_name = f"project_{project_id}"

        # Check if graph exists
        existing_graphs = self.db.list_graphs()
        if graph_name not in existing_graphs:
            raise RuntimeError(
                f"Project '{project_id}' does not exist. "
                f"Create it first with create_project('{project_id}')"
            )

        # Retrieve or create graph handle
        if graph_name not in self._cache:
            self._cache[graph_name] = self.db.select_graph(graph_name)
            logger.debug("graph_handle_cached", graph_name=graph_name)

        # Create and set active context
        self._active = ProjectContext(
            project_id=project_id,
            graph_name=graph_name,
            graph=self._cache[graph_name],
            metadata=metadata or {}
        )

        logger.info(
            "project_mounted",
            project_id=project_id,
            graph_name=graph_name,
            user_id=user_id,  # NEW: Phase 2
            rbac_enabled=bool(self.access_control and user_id)
        )

        return self._active

    def unmount(self):
        """
        Unmount the current project context.

        After unmounting, any query attempts will raise RuntimeError.
        This is a safety feature to prevent accidental cross-contamination.

        Example:
            >>> manager.mount("client_a")
            >>> # ... work with Client A ...
            >>> manager.unmount()
            >>> manager.query("...")  # RuntimeError: No project mounted
        """
        if self._active:
            logger.info(
                "project_unmounted",
                project_id=self._active.project_id
            )
            self._active = None
        else:
            logger.debug("unmount_called_with_no_active_context")

    @property
    def current(self) -> ProjectContext:
        """
        Get the currently mounted project context.

        Raises:
            RuntimeError: If no project is mounted

        Returns:
            Active ProjectContext

        Example:
            >>> context = manager.current
            >>> print(context.project_id)
            'client_a'
        """
        if not self._active:
            raise RuntimeError(
                "No project context mounted. "
                "Call mount('project_id') before querying. "
                "This prevents accidental cross-project data leakage."
            )
        return self._active

    def query(self, cypher: str, params: Optional[Dict] = None) -> object:
        """
        Execute a Cypher query on the currently mounted project graph.

        SAFETY: This method enforces that a project is mounted.
        You CANNOT accidentally query the wrong project's data.

        Args:
            cypher: Cypher query string
            params: Optional query parameters dict

        Returns:
            Query result object from FalkorDB

        Raises:
            RuntimeError: If no project is mounted

        Example:
            >>> manager.mount("client_a")
            >>> result = manager.query(
            ...     "MATCH (s:SAPSystem {sid: $sid}) RETURN s",
            ...     params={"sid": "PRD"}
            ... )
        """
        # Enforce active context
        context = self.current

        # Execute query on the active graph
        try:
            result = context.graph.query(cypher, params or {})
            logger.debug(
                "query_executed",
                project_id=context.project_id,
                query_preview=cypher[:100]
            )
            return result
        except Exception as e:
            logger.error(
                "query_failed",
                project_id=context.project_id,
                error=str(e),
                query=cypher[:200]
            )
            raise

    async def create_project_async(
        self,
        project_id: str,
        clone_from: Optional[str] = None,
        metadata: Optional[Dict] = None,
        user_id: Optional[str] = None  # NEW: Phase 2
    ) -> ProjectContext:
        """
        Create a new project with its own isolated graph (async version for RBAC).

        ISOLATION: Each project gets a completely separate FalkorDB graph.
        Think of it as creating a new "brain partition" for Veda.

        RBAC: Only admins can create projects (Phase 2).

        Args:
            project_id: Unique project identifier
            clone_from: Optional graph name to clone from (e.g., "sap_ontology_base")
            metadata: Optional project metadata
            user_id: User identifier for RBAC check (Phase 2)

        Returns:
            ProjectContext for the newly created project

        Raises:
            ValueError: If project_id is invalid or already exists
            PermissionError: If user lacks admin permission (Phase 2)

        Example:
            >>> await manager.create_project_async("client_b", user_id="admin")
        """
        # Phase 2: Check admin permission
        if user_id and self.access_control:
            # For project creation, we need to check if user is admin on ANY project
            # Or if this is the first project, allow it
            existing_projects = self.list_projects()
            
            if existing_projects:
                # Check if user is admin on at least one project
                has_admin_somewhere = False
                for existing_proj in existing_projects:
                    try:
                        if await self.access_control.can_manage_users(user_id, existing_proj):
                            has_admin_somewhere = True
                            break
                    except:
                        continue
                
                if not has_admin_somewhere:
                    raise PermissionError(
                        f"User '{user_id}' lacks admin permissions. "
                        f"Only admins can create projects."
                    )
            
            logger.debug(
                "create_project_permission_granted",
                user_id=user_id,
                project_id=project_id
            )

        # Validate project ID
        self.validate_project_id(project_id)

        graph_name = f"project_{project_id}"

        # Check if already exists
        if graph_name in self.db.list_graphs():
            raise ValueError(
                f"Project '{project_id}' already exists. "
                f"Use mount('{project_id}') to switch to it."
            )

        # Create new graph
        try:
            if clone_from:
                # Clone from template
                logger.info(
                    "cloning_project_from_template",
                    project_id=project_id,
                    template=clone_from,
                    user_id=user_id  # NEW
                )

                # Verify template exists
                if clone_from not in self.db.list_graphs():
                    raise ValueError(f"Template graph '{clone_from}' does not exist")

                # FalkorDB's native copy operation
                template_graph = self.db.select_graph(clone_from)
                new_graph = template_graph.copy(graph_name)

                # Verify the clone was created successfully
                new_graph.query("MATCH (n) RETURN count(n) LIMIT 1")
                logger.debug("graph_cloned", graph_name=graph_name)
            else:
                # Create empty graph
                logger.info(
                    "creating_empty_project",
                    project_id=project_id,
                    user_id=user_id  # NEW
                )
                new_graph = self.db.select_graph(graph_name)

                # Force graph creation by executing a dummy query
                # FalkorDB creates graphs lazily, so we need to write something
                new_graph.query("CREATE (:_InitMarker {initialized: true})")
                logger.debug("graph_initialized", graph_name=graph_name)

            # Cache the graph handle
            self._cache[graph_name] = new_graph

            logger.info(
                "project_created",
                project_id=project_id,
                graph_name=graph_name,
                cloned_from=clone_from,
                user_id=user_id,  # NEW
                rbac_enabled=bool(self.access_control and user_id)
            )

            # Phase 2: Auto-grant admin access to creator
            if user_id and self.access_control:
                await self.access_control.grant_access(
                    user_id=user_id,
                    project_id=project_id,
                    role="admin",
                    granted_by=user_id  # Self-grant on creation
                )
                logger.info(
                    "project_creator_granted_admin",
                    user_id=user_id,
                    project_id=project_id
                )

            # Auto-mount the new project
            return self.mount(project_id, metadata=metadata, user_id=user_id)

        except Exception as e:
            logger.error(
                "project_creation_failed",
                project_id=project_id,
                error=str(e)
            )
            raise RuntimeError(f"Failed to create project '{project_id}': {e}")

    def create_project(
        self,
        project_id: str,
        clone_from: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> ProjectContext:
        """
        Create a new project (synchronous version, backward compatible).

        For RBAC support, use create_project_async() instead.

        Args:
            project_id: Unique project identifier
            clone_from: Optional graph name to clone from
            metadata: Optional project metadata

        Returns:
            ProjectContext for the newly created project

        Example:
            >>> manager.create_project("client_a")  # Phase 1
        """
        # Validate project ID
        self.validate_project_id(project_id)

        graph_name = f"project_{project_id}"

        # Check if already exists
        if graph_name in self.db.list_graphs():
            raise ValueError(
                f"Project '{project_id}' already exists. "
                f"Use mount('{project_id}') to switch to it."
            )

        # Create new graph
        try:
            if clone_from:
                # Clone from template
                logger.info(
                    "cloning_project_from_template",
                    project_id=project_id,
                    template=clone_from
                )

                # Verify template exists
                if clone_from not in self.db.list_graphs():
                    raise ValueError(f"Template graph '{clone_from}' does not exist")

                # FalkorDB's native copy operation
                template_graph = self.db.select_graph(clone_from)
                new_graph = template_graph.copy(graph_name)

                # Verify the clone was created successfully
                new_graph.query("MATCH (n) RETURN count(n) LIMIT 1")
                logger.debug("graph_cloned", graph_name=graph_name)
            else:
                # Create empty graph
                logger.info(
                    "creating_empty_project",
                    project_id=project_id
                )
                new_graph = self.db.select_graph(graph_name)

                # Force graph creation by executing a dummy query
                # FalkorDB creates graphs lazily, so we need to write something
                new_graph.query("CREATE (:_InitMarker {initialized: true})")
                logger.debug("graph_initialized", graph_name=graph_name)

            # Cache the graph handle
            self._cache[graph_name] = new_graph

            logger.info(
                "project_created",
                project_id=project_id,
                graph_name=graph_name,
                cloned_from=clone_from
            )

            # Auto-mount the new project
            return self.mount(project_id, metadata=metadata)

        except Exception as e:
            logger.error(
                "project_creation_failed",
                project_id=project_id,
                error=str(e)
            )
            raise RuntimeError(f"Failed to create project '{project_id}': {e}")

    async def delete_project_async(
        self,
        project_id: str,
        confirm: bool = False,
        user_id: Optional[str] = None  # NEW: Phase 2
    ):
        """
        Delete a project and its graph (async version for RBAC).

        ⚠️ WARNING: This is DESTRUCTIVE and IRREVERSIBLE.
        All landscape data for this project will be permanently lost.

        RBAC: Only admins can delete projects (Phase 2).

        Args:
            project_id: Project to delete
            confirm: Must be True to actually delete (safety check)
            user_id: User identifier for RBAC check (Phase 2)

        Raises:
            ValueError: If project is reserved or confirm=False
            RuntimeError: If deletion fails
            PermissionError: If user lacks admin permission (Phase 2)

        Example:
            >>> await manager.delete_project_async("old_client", confirm=True, user_id="admin")
        """
        if not confirm:
            raise ValueError(
                f"To delete project '{project_id}', you must pass confirm=True. "
                "This is a destructive operation that cannot be undone."
            )

        # Validate and check reserved
        self.validate_project_id(project_id)

        # Phase 2: Check admin permission
        if user_id and self.access_control:
            if not await self.access_control.can_manage_users(user_id, project_id):
                raise PermissionError(
                    f"User '{user_id}' lacks admin permissions for project '{project_id}'. "
                    f"Only admins can delete projects."
                )
            
            logger.debug(
                "delete_project_permission_granted",
                user_id=user_id,
                project_id=project_id
            )

        graph_name = f"project_{project_id}"

        # Unmount if currently active
        if self._active and self._active.project_id == project_id:
            self.unmount()

        # Remove from cache
        if graph_name in self._cache:
            del self._cache[graph_name]

        # Delete the graph
        try:
            self.db.select_graph(graph_name).delete()
            logger.warning(
                "project_deleted",
                project_id=project_id,
                graph_name=graph_name,
                user_id=user_id,  # NEW
                rbac_enabled=bool(self.access_control and user_id)
            )
        except Exception as e:
            logger.error(
                "project_deletion_failed",
                project_id=project_id,
                error=str(e)
            )
            raise RuntimeError(f"Failed to delete project '{project_id}': {e}")

    def delete_project(self, project_id: str, confirm: bool = False):
        """
        Delete a project (synchronous version, backward compatible).

        For RBAC support, use delete_project_async() instead.

        ⚠️ WARNING: This is DESTRUCTIVE and IRREVERSIBLE.

        Args:
            project_id: Project to delete
            confirm: Must be True to actually delete

        Example:
            >>> manager.delete_project("old_client", confirm=True)  # Phase 1
        """
        if not confirm:
            raise ValueError(
                f"To delete project '{project_id}', you must pass confirm=True. "
                "This is a destructive operation that cannot be undone."
            )

        # Validate and check reserved
        self.validate_project_id(project_id)

        graph_name = f"project_{project_id}"

        # Unmount if currently active
        if self._active and self._active.project_id == project_id:
            self.unmount()

        # Remove from cache
        if graph_name in self._cache:
            del self._cache[graph_name]

        # Delete the graph
        try:
            self.db.select_graph(graph_name).delete()
            logger.warning(
                "project_deleted",
                project_id=project_id,
                graph_name=graph_name
            )
        except Exception as e:
            logger.error(
                "project_deletion_failed",
                project_id=project_id,
                error=str(e)
            )
            raise RuntimeError(f"Failed to delete project '{project_id}': {e}")

    def list_projects(self) -> List[str]:
        """
        List all available projects.

        Returns:
            List of project IDs (without "project_" prefix)

        Example:
            >>> manager.list_projects()
            ['client_a', 'client_b', 'customer_123']
        """
        all_graphs = self.db.list_graphs()

        # Filter for project graphs (exclude system graphs)
        project_graphs = [
            g.replace("project_", "")
            for g in all_graphs
            if g.startswith("project_")
        ]

        logger.debug("projects_listed", count=len(project_graphs))
        return sorted(project_graphs)

    def get_project_info(self, project_id: str) -> Dict:
        """
        Get information about a project.

        Args:
            project_id: Project identifier

        Returns:
            Dict with project metadata and statistics

        Example:
            >>> info = manager.get_project_info("client_a")
            >>> print(info['node_count'])
            150
        """
        self.validate_project_id(project_id)

        graph_name = f"project_{project_id}"

        if graph_name not in self.db.list_graphs():
            raise ValueError(f"Project '{project_id}' does not exist")

        # Get graph handle
        graph = self._cache.get(graph_name) or self.db.select_graph(graph_name)

        # Query for basic stats
        try:
            node_count_result = graph.query("MATCH (n) RETURN count(n) as count")
            node_count = node_count_result.result_set[0][0] if node_count_result.result_set else 0

            edge_count_result = graph.query("MATCH ()-[r]->() RETURN count(r) as count")
            edge_count = edge_count_result.result_set[0][0] if edge_count_result.result_set else 0

            return {
                "project_id": project_id,
                "graph_name": graph_name,
                "node_count": node_count,
                "edge_count": edge_count,
                "exists": True,
                "is_mounted": self._active and self._active.project_id == project_id
            }
        except Exception as e:
            logger.error(
                "project_info_retrieval_failed",
                project_id=project_id,
                error=str(e)
            )
            return {
                "project_id": project_id,
                "graph_name": graph_name,
                "error": str(e),
                "exists": True,
                "is_mounted": False
            }

# End of ProjectContextManager implementation
