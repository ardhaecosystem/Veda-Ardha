"""
Veda 4.0 - Phase 2 Week 2: Project Management Service

High-level project management operations.
User-friendly API for project lifecycle, bulk operations, and metadata.

FIXED VERSION: Added _get_project_stats_direct() helper method
to work around missing get_project_statistics() in ProjectContextManager.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import structlog

logger = structlog.get_logger()


class ProjectStatus(Enum):
    """Project status."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    READONLY = "READONLY"
    MAINTENANCE = "MAINTENANCE"


@dataclass
class ProjectMetadata:
    """Project metadata."""
    project_id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    owner: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "owner": self.owner,
            "tags": self.tags
        }


@dataclass
class ProjectInfo:
    """Complete project information."""
    metadata: ProjectMetadata
    statistics: Dict[str, Any]
    health_score: Optional[float] = None
    last_accessed: Optional[datetime] = None
    
    def __str__(self) -> str:
        return (
            f"{self.metadata.name} ({self.metadata.project_id}) | "
            f"Status: {self.metadata.status.value} | "
            f"Systems: {self.statistics.get('total_systems', 0)} | "
            f"Instances: {self.statistics.get('total_instances', 0)}"
        )


@dataclass
class BulkOperationResult:
    """Result of a bulk operation."""
    total: int
    successful: int
    failed: int
    errors: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100
    
    def __str__(self) -> str:
        return (
            f"Total: {self.total} | "
            f"Successful: {self.successful} | "
            f"Failed: {self.failed} | "
            f"Success Rate: {self.success_rate:.1f}%"
        )


class ProjectService:
    """
    High-level project management service.
    
    Provides user-friendly operations for project lifecycle,
    bulk operations, and metadata management.
    """
    
    def __init__(
        self,
        project_manager,  # ProjectContextManager
        access_control=None  # Optional AccessControl for RBAC
    ):
        """
        Initialize project service.
        
        Args:
            project_manager: ProjectContextManager instance
            access_control: Optional AccessControl instance (Phase 2)
        """
        self.project_manager = project_manager
        self.access_control = access_control
        
        # Metadata storage (in-memory for now, could be Redis/DB)
        self._metadata_cache: Dict[str, ProjectMetadata] = {}
        
        logger.info(
            "project_service_initialized",
            rbac_enabled=access_control is not None
        )
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_project_stats_direct(self, project_id: str) -> Dict[str, Any]:
        """
        Get project statistics by querying the graph directly.
        
        This is a workaround since get_project_statistics() doesn't exist
        on ProjectContextManager yet.
        
        Args:
            project_id: Project to query
        
        Returns:
            Dict with total_systems, total_instances, total_hosts
        """
        try:
            # Mount project
            self.project_manager.mount(project_id)
            
            # Count systems
            try:
                system_result = self.project_manager.query(
                    "MATCH (n:SAPSystem) RETURN count(n) as count"
                )
                system_count = system_result.result_set[0][0] if system_result.result_set else 0
            except Exception:
                system_count = 0
            
            # Count instances
            try:
                instance_result = self.project_manager.query(
                    "MATCH (n:SAPInstance) RETURN count(n) as count"
                )
                instance_count = instance_result.result_set[0][0] if instance_result.result_set else 0
            except Exception:
                instance_count = 0
            
            # Count hosts
            try:
                host_result = self.project_manager.query(
                    "MATCH (n:Host) RETURN count(n) as count"
                )
                host_count = host_result.result_set[0][0] if host_result.result_set else 0
            except Exception:
                host_count = 0
            
            stats = {
                'total_systems': system_count,
                'total_instances': instance_count,
                'total_hosts': host_count,
            }
            
            logger.debug(
                "project_stats_retrieved",
                project_id=project_id,
                **stats
            )
            
            return stats
            
        except Exception as e:
            logger.error("stats_query_error", error=str(e), project_id=project_id)
            return {
                'total_systems': 0,
                'total_instances': 0,
                'total_hosts': 0,
            }
    
    # =========================================================================
    # PROJECT LIFECYCLE
    # =========================================================================
    
    def create_project(
        self,
        project_id: str,
        name: str,
        description: str = "",
        clone_from: Optional[str] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> ProjectInfo:
        """
        Create a new project.
        
        Args:
            project_id: Unique project identifier
            name: Human-readable project name
            description: Project description
            clone_from: Optional template to clone from
            user_id: User creating the project (for RBAC)
            tags: Optional project tags
        
        Returns:
            ProjectInfo object
        """
        logger.info(
            "creating_project",
            project_id=project_id,
            name=name,
            clone_from=clone_from,
            user_id=user_id
        )
        
        # Create project in context manager
        if self.access_control and user_id:
            # Phase 2: Use RBAC-aware creation
            import asyncio
            context = asyncio.run(
                self.project_manager.create_project_async(
                    project_id,
                    user_id,
                    clone_from
                )
            )
        else:
            # Phase 1: Simple creation
            context = self.project_manager.create_project(
                project_id,
                clone_from
            )
        
        # Create metadata
        metadata = ProjectMetadata(
            project_id=project_id,
            name=name,
            description=description,
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by=user_id,
            owner=user_id,
            tags=tags or []
        )
        
        # Cache metadata
        self._metadata_cache[project_id] = metadata
        
        # Get initial statistics (using direct query)
        stats = self._get_project_stats_direct(project_id)
        
        project_info = ProjectInfo(
            metadata=metadata,
            statistics=stats,
            last_accessed=datetime.now()
        )
        
        logger.info(
            "project_created",
            project_id=project_id,
            name=name
        )
        
        return project_info
    
    def archive_project(
        self,
        project_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Archive a project (mark as archived, don't delete).
        
        Args:
            project_id: Project to archive
            user_id: User performing the action (for RBAC)
        
        Returns:
            True if successful
        """
        logger.info(
            "archiving_project",
            project_id=project_id,
            user_id=user_id
        )
        
        # Check permissions if RBAC enabled
        if self.access_control and user_id:
            import asyncio
            can_delete = asyncio.run(
                self.access_control.can_delete(user_id, project_id)
            )
            if not can_delete:
                raise PermissionError(
                    f"User {user_id} does not have permission to archive {project_id}"
                )
        
        # Update metadata
        if project_id in self._metadata_cache:
            self._metadata_cache[project_id].status = ProjectStatus.ARCHIVED
            self._metadata_cache[project_id].updated_at = datetime.now()
        
        logger.info("project_archived", project_id=project_id)
        return True
    
    def delete_project(
        self,
        project_id: str,
        user_id: Optional[str] = None,
        force: bool = False
    ) -> bool:
        """
        Permanently delete a project.
        
        Args:
            project_id: Project to delete
            user_id: User performing the action (for RBAC)
            force: If True, skip safety checks
        
        Returns:
            True if successful
        
        Warning:
            This is permanent! Consider archive_project() instead.
        """
        logger.warning(
            "deleting_project",
            project_id=project_id,
            user_id=user_id,
            force=force
        )
        
        # Check permissions if RBAC enabled
        if self.access_control and user_id:
            import asyncio
            can_delete = asyncio.run(
                self.access_control.can_delete(user_id, project_id)
            )
            if not can_delete:
                raise PermissionError(
                    f"User {user_id} does not have permission to delete {project_id}"
                )
        
        # Safety check: Require archived first (unless force)
        if not force and project_id in self._metadata_cache:
            if self._metadata_cache[project_id].status != ProjectStatus.ARCHIVED:
                raise ValueError(
                    f"Project {project_id} must be archived before deletion. "
                    "Use force=True to bypass."
                )
        
        # Delete from context manager
        if self.access_control and user_id:
            # Phase 2: Use RBAC-aware deletion
            import asyncio
            asyncio.run(
                self.project_manager.delete_project_async(
                    project_id,
                    user_id
                )
            )
        else:
            # Phase 1: Simple deletion
            self.project_manager.delete_project(project_id)
        
        # Remove from metadata cache
        if project_id in self._metadata_cache:
            del self._metadata_cache[project_id]
        
        logger.warning("project_deleted", project_id=project_id)
        return True
    
    # =========================================================================
    # PROJECT QUERIES
    # =========================================================================
    
    def get_project_info(
        self,
        project_id: str,
        include_health: bool = False
    ) -> ProjectInfo:
        """
        Get complete project information.
        
        Args:
            project_id: Project to query
            include_health: If True, calculate health score
        
        Returns:
            ProjectInfo object
        """
        # Get metadata (from cache or create default)
        metadata = self._metadata_cache.get(
            project_id,
            ProjectMetadata(
                project_id=project_id,
                name=project_id,
                status=ProjectStatus.ACTIVE
            )
        )
        
        # Get statistics (using direct query)
        stats = self._get_project_stats_direct(project_id)
        
        # Calculate health if requested
        health_score = None
        if include_health:
            try:
                from .knowledge_service import SAPKnowledgeService
                service = SAPKnowledgeService(self.project_manager, project_id)
                health = service.get_landscape_health()
                health_score = health.health_score
            except Exception as e:
                logger.warning(
                    "health_calculation_failed",
                    project_id=project_id,
                    error=str(e)
                )
        
        project_info = ProjectInfo(
            metadata=metadata,
            statistics=stats,
            health_score=health_score,
            last_accessed=datetime.now()
        )
        
        return project_info
    
    def list_all_projects(
        self,
        include_archived: bool = False,
        user_id: Optional[str] = None
    ) -> List[ProjectInfo]:
        """
        List all projects.
        
        Args:
            include_archived: If True, include archived projects
            user_id: Optional user ID (for RBAC filtering)
        
        Returns:
            List of ProjectInfo objects
        """
        # Get all projects from context manager
        project_ids = self.project_manager.list_projects()
        
        # Filter by user permissions if RBAC enabled
        if self.access_control and user_id:
            import asyncio
            accessible_projects = asyncio.run(
                self.access_control.get_user_projects(user_id)
            )
            project_ids = [p for p in project_ids if p in accessible_projects]
        
        # Get info for each project
        projects = []
        for project_id in project_ids:
            try:
                info = self.get_project_info(project_id)
                
                # Filter archived if requested
                if not include_archived and info.metadata.status == ProjectStatus.ARCHIVED:
                    continue
                
                projects.append(info)
            except Exception as e:
                logger.warning(
                    "failed_to_get_project_info",
                    project_id=project_id,
                    error=str(e)
                )
        
        logger.debug(
            "projects_listed",
            total=len(projects),
            user_id=user_id
        )
        
        return projects
    
    def search_projects(
        self,
        query: str,
        user_id: Optional[str] = None
    ) -> List[ProjectInfo]:
        """
        Search projects by name, description, or tags.
        
        Args:
            query: Search query
            user_id: Optional user ID (for RBAC filtering)
        
        Returns:
            List of matching ProjectInfo objects
        """
        all_projects = self.list_all_projects(
            include_archived=True,
            user_id=user_id
        )
        
        query_lower = query.lower()
        matches = []
        
        for project in all_projects:
            # Search in name, description, tags
            if (query_lower in project.metadata.name.lower() or
                query_lower in project.metadata.description.lower() or
                any(query_lower in tag.lower() for tag in project.metadata.tags)):
                matches.append(project)
        
        logger.debug(
            "projects_searched",
            query=query,
            matches=len(matches)
        )
        
        return matches
    
    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================
    
    def clone_project(
        self,
        source_project_id: str,
        target_project_id: str,
        user_id: Optional[str] = None
    ) -> ProjectInfo:
        """
        Clone a project.
        
        Args:
            source_project_id: Project to clone from
            target_project_id: New project ID
            user_id: User performing the action
        
        Returns:
            ProjectInfo for new project
        """
        logger.info(
            "cloning_project",
            source=source_project_id,
            target=target_project_id,
            user_id=user_id
        )
        
        # Get source metadata
        source_info = self.get_project_info(source_project_id)
        
        # Create new project as clone
        target_info = self.create_project(
            project_id=target_project_id,
            name=f"{source_info.metadata.name} (Clone)",
            description=f"Cloned from {source_project_id}",
            clone_from=source_project_id,
            user_id=user_id,
            tags=source_info.metadata.tags + ["clone"]
        )
        
        logger.info(
            "project_cloned",
            source=source_project_id,
            target=target_project_id
        )
        
        return target_info
    
    def bulk_archive(
        self,
        project_ids: List[str],
        user_id: Optional[str] = None
    ) -> BulkOperationResult:
        """
        Archive multiple projects.
        
        Args:
            project_ids: List of projects to archive
            user_id: User performing the action
        
        Returns:
            BulkOperationResult
        """
        result = BulkOperationResult(
            total=len(project_ids),
            successful=0,
            failed=0
        )
        
        for project_id in project_ids:
            try:
                self.archive_project(project_id, user_id)
                result.successful += 1
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{project_id}: {str(e)}")
                logger.error(
                    "bulk_archive_error",
                    project_id=project_id,
                    error=str(e)
                )
        
        logger.info(
            "bulk_archive_complete",
            total=result.total,
            successful=result.successful,
            failed=result.failed
        )
        
        return result
    
    # =========================================================================
    # METADATA MANAGEMENT
    # =========================================================================
    
    def update_metadata(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[ProjectStatus] = None
    ) -> ProjectMetadata:
        """
        Update project metadata.
        
        Args:
            project_id: Project to update
            name: Optional new name
            description: Optional new description
            tags: Optional new tags
            status: Optional new status
        
        Returns:
            Updated ProjectMetadata
        """
        # Get existing metadata
        metadata = self._metadata_cache.get(
            project_id,
            ProjectMetadata(project_id=project_id, name=project_id)
        )
        
        # Update fields
        if name:
            metadata.name = name
        if description:
            metadata.description = description
        if tags:
            metadata.tags = tags
        if status:
            metadata.status = status
        
        metadata.updated_at = datetime.now()
        
        # Update cache
        self._metadata_cache[project_id] = metadata
        
        logger.info(
            "metadata_updated",
            project_id=project_id
        )
        
        return metadata
    
    def add_tags(
        self,
        project_id: str,
        tags: List[str]
    ) -> ProjectMetadata:
        """
        Add tags to a project.
        
        Args:
            project_id: Project to tag
            tags: Tags to add
        
        Returns:
            Updated ProjectMetadata
        """
        metadata = self._metadata_cache.get(
            project_id,
            ProjectMetadata(project_id=project_id, name=project_id)
        )
        
        # Add new tags (avoid duplicates)
        for tag in tags:
            if tag not in metadata.tags:
                metadata.tags.append(tag)
        
        metadata.updated_at = datetime.now()
        self._metadata_cache[project_id] = metadata
        
        logger.debug(
            "tags_added",
            project_id=project_id,
            tags=tags
        )
        
        return metadata
    
    # =========================================================================
    # STATISTICS & REPORTING
    # =========================================================================
    
    def get_global_statistics(self) -> Dict[str, Any]:
        """
        Get statistics across all projects.
        
        Returns:
            Dict with global metrics
        """
        all_projects = self.list_all_projects(include_archived=True)
        
        total_systems = 0
        total_instances = 0
        total_hosts = 0
        
        for project in all_projects:
            total_systems += project.statistics.get('total_systems', 0)
            total_instances += project.statistics.get('total_instances', 0)
            total_hosts += project.statistics.get('total_hosts', 0)
        
        stats = {
            'total_projects': len(all_projects),
            'active_projects': sum(
                1 for p in all_projects 
                if p.metadata.status == ProjectStatus.ACTIVE
            ),
            'archived_projects': sum(
                1 for p in all_projects 
                if p.metadata.status == ProjectStatus.ARCHIVED
            ),
            'total_systems': total_systems,
            'total_instances': total_instances,
            'total_hosts': total_hosts,
            'generated_at': datetime.now().isoformat()
        }
        
        return stats
    
    def generate_summary_report(self) -> str:
        """
        Generate summary report for all projects.
        
        Returns:
            Formatted report string
        """
        stats = self.get_global_statistics()
        projects = self.list_all_projects(include_archived=False)
        
        report = []
        report.append("=" * 70)
        report.append("VEDA PROJECT MANAGEMENT SUMMARY")
        report.append("=" * 70)
        report.append(f"Generated: {stats['generated_at']}")
        report.append("")
        
        # Global stats
        report.append("GLOBAL STATISTICS")
        report.append("-" * 70)
        report.append(f"Total Projects: {stats['total_projects']}")
        report.append(f"Active Projects: {stats['active_projects']}")
        report.append(f"Archived Projects: {stats['archived_projects']}")
        report.append(f"Total Systems: {stats['total_systems']}")
        report.append(f"Total Instances: {stats['total_instances']}")
        report.append(f"Total Hosts: {stats['total_hosts']}")
        report.append("")
        
        # Active projects
        if projects:
            report.append("ACTIVE PROJECTS")
            report.append("-" * 70)
            for project in projects:
                report.append(f"• {project.metadata.name} ({project.metadata.project_id})")
                report.append(f"  Systems: {project.statistics.get('total_systems', 0)}")
                report.append(f"  Instances: {project.statistics.get('total_instances', 0)}")
                report.append(f"  Status: {project.metadata.status.value}")
                report.append("")
        
        report.append("=" * 70)
        
        return "\n".join(report)


# Convenience function
def create_project_service(
    project_manager,
    access_control=None
) -> ProjectService:
    """
    Create project service instance.
    
    Args:
        project_manager: ProjectContextManager instance
        access_control: Optional AccessControl instance
    
    Returns:
        ProjectService instance
    """
    return ProjectService(project_manager, access_control)
