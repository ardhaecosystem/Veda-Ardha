"""
Veda 4.0 - Phase 2: Access Control (Layer 4)

Role-Based Access Control (RBAC) for multi-project isolation.
Provides user → project → role mappings with permission checking.

SECURITY FEATURES:
- Three-tier role system (admin, editor, viewer)
- Redis-backed permission cache (5-minute TTL)
- Comprehensive audit logging
- Project ownership tracking
- Permission inheritance

ROLES:
- admin: Full access (create/delete projects, manage users, all data operations)
- editor: Read/write access to project data, cannot manage users
- viewer: Read-only access to project data

USAGE:
    access_control = AccessControl(redis_url="redis://localhost:6380")
    await access_control.initialize()
    
    # Grant permissions
    await access_control.grant_access("user123", "client_acme", "editor")
    
    # Check permissions
    if access_control.can_read("user123", "client_acme"):
        # Perform read operation
        pass
"""

import asyncio
from typing import Dict, List, Optional, Set, Literal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

import redis.asyncio as redis
import structlog

logger = structlog.get_logger()


class Role(Enum):
    """User roles with hierarchical permissions."""
    ADMIN = "admin"      # Full access to everything
    EDITOR = "editor"    # Read/write to project data
    VIEWER = "viewer"    # Read-only access


class Permission(Enum):
    """Granular permissions."""
    # Project management
    CREATE_PROJECT = "create_project"
    DELETE_PROJECT = "delete_project"
    ARCHIVE_PROJECT = "archive_project"
    
    # Data operations
    READ_DATA = "read_data"
    WRITE_DATA = "write_data"
    DELETE_DATA = "delete_data"
    
    # User management
    GRANT_ACCESS = "grant_access"
    REVOKE_ACCESS = "revoke_access"
    
    # System operations
    VIEW_AUDIT_LOG = "view_audit_log"
    MANAGE_TEMPLATES = "manage_templates"


# Permission matrix: Role → Set of Permissions
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        # Project management
        Permission.CREATE_PROJECT,
        Permission.DELETE_PROJECT,
        Permission.ARCHIVE_PROJECT,
        # Data operations
        Permission.READ_DATA,
        Permission.WRITE_DATA,
        Permission.DELETE_DATA,
        # User management
        Permission.GRANT_ACCESS,
        Permission.REVOKE_ACCESS,
        # System operations
        Permission.VIEW_AUDIT_LOG,
        Permission.MANAGE_TEMPLATES,
    },
    Role.EDITOR: {
        # Data operations only
        Permission.READ_DATA,
        Permission.WRITE_DATA,
        Permission.DELETE_DATA,
    },
    Role.VIEWER: {
        # Read-only
        Permission.READ_DATA,
    },
}


@dataclass
class AccessGrant:
    """
    Represents a user's access grant to a project.
    
    Attributes:
        user_id: User identifier
        project_id: Project identifier
        role: User's role in this project
        granted_by: User who granted this access
        granted_at: Timestamp of grant
        expires_at: Optional expiration timestamp
    """
    user_id: str
    project_id: str
    role: Role
    granted_by: str
    granted_at: datetime
    expires_at: Optional[datetime] = None


@dataclass
class AuditLogEntry:
    """
    Audit log entry for access control events.
    
    Attributes:
        timestamp: When the event occurred
        user_id: User who performed the action
        action: What action was performed
        project_id: Which project was affected
        target_user_id: If action affects another user
        result: success or denied
        details: Additional context
    """
    timestamp: datetime
    user_id: str
    action: str
    project_id: str
    target_user_id: Optional[str] = None
    result: Literal["success", "denied"] = "success"
    details: Dict = field(default_factory=dict)


class AccessControl:
    """
    Role-Based Access Control system for Veda 4.0.
    
    Manages user permissions across multiple projects with Redis-backed caching.
    
    Architecture:
    - Layer 4 (RBAC): This file
    - Layer 2 (Context): context_manager.py
    - Layer 1 (Network): FalkorDB multi-graph
    
    Features:
    - Three-tier role system (admin/editor/viewer)
    - Redis cache for fast permission checks (5-minute TTL)
    - Comprehensive audit logging
    - Project ownership tracking
    - Permission inheritance
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6380",
        cache_ttl_seconds: int = 300,  # 5 minutes
        enable_audit_log: bool = True
    ):
        """
        Initialize access control system.
        
        Args:
            redis_url: Redis connection URL
            cache_ttl_seconds: How long to cache permissions (default 5 minutes)
            enable_audit_log: Whether to log access events
        """
        self.redis_url = redis_url
        self.cache_ttl = cache_ttl_seconds
        self.enable_audit_log = enable_audit_log
        
        self.redis_client: Optional[redis.Redis] = None
        
        # In-memory cache for super-fast checks (falls back to Redis)
        self._memory_cache: Dict[str, AccessGrant] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        logger.info(
            "access_control_initialized",
            cache_ttl_seconds=cache_ttl_seconds,
            audit_enabled=enable_audit_log
        )
    
    async def initialize(self):
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                encoding="utf-8"
            )
            
            # Test connection
            await self.redis_client.ping()
            
            logger.info("redis_connection_established", url=self.redis_url)
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e), url=self.redis_url)
            raise
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("redis_connection_closed")
    
    # ========================================================================
    # ACCESS GRANT MANAGEMENT
    # ========================================================================
    
    async def grant_access(
        self,
        user_id: str,
        project_id: str,
        role: str,
        granted_by: str,
        expires_at: Optional[datetime] = None
    ) -> AccessGrant:
        """
        Grant a user access to a project.
        
        Args:
            user_id: User to grant access to
            project_id: Project to grant access for
            role: Role to grant (admin/editor/viewer)
            granted_by: User performing the grant
            expires_at: Optional expiration timestamp
        
        Returns:
            AccessGrant object
        
        Raises:
            ValueError: If role is invalid
            PermissionError: If granted_by lacks permission
        """
        # Validate role
        try:
            role_enum = Role(role.lower())
        except ValueError:
            raise ValueError(f"Invalid role: {role}. Must be admin, editor, or viewer")
        
        # Check if grantor has permission
        if not await self.has_permission(granted_by, project_id, Permission.GRANT_ACCESS):
            await self._audit_log(
                user_id=granted_by,
                action="grant_access",
                project_id=project_id,
                target_user_id=user_id,
                result="denied",
                details={"reason": "insufficient_permissions"}
            )
            raise PermissionError(f"User {granted_by} cannot grant access to project {project_id}")
        
        # Create grant
        grant = AccessGrant(
            user_id=user_id,
            project_id=project_id,
            role=role_enum,
            granted_by=granted_by,
            granted_at=datetime.now(),
            expires_at=expires_at
        )
        
        # Store in Redis
        await self._store_grant(grant)
        
        # Invalidate cache
        self._invalidate_cache(user_id, project_id)
        
        # Audit log
        await self._audit_log(
            user_id=granted_by,
            action="grant_access",
            project_id=project_id,
            target_user_id=user_id,
            result="success",
            details={"role": role, "expires_at": expires_at.isoformat() if expires_at else None}
        )
        
        logger.info(
            "access_granted",
            user_id=user_id,
            project_id=project_id,
            role=role,
            granted_by=granted_by
        )
        
        return grant
    
    async def revoke_access(
        self,
        user_id: str,
        project_id: str,
        revoked_by: str
    ) -> bool:
        """
        Revoke a user's access to a project.
        
        Args:
            user_id: User to revoke access from
            project_id: Project to revoke access for
            revoked_by: User performing the revocation
        
        Returns:
            True if revoked, False if no access existed
        
        Raises:
            PermissionError: If revoked_by lacks permission
        """
        # Check if revoker has permission
        if not await self.has_permission(revoked_by, project_id, Permission.REVOKE_ACCESS):
            await self._audit_log(
                user_id=revoked_by,
                action="revoke_access",
                project_id=project_id,
                target_user_id=user_id,
                result="denied",
                details={"reason": "insufficient_permissions"}
            )
            raise PermissionError(f"User {revoked_by} cannot revoke access to project {project_id}")
        
        # Delete from Redis
        key = self._grant_key(user_id, project_id)
        deleted = await self.redis_client.delete(key)
        
        # Invalidate cache
        self._invalidate_cache(user_id, project_id)
        
        # Audit log
        await self._audit_log(
            user_id=revoked_by,
            action="revoke_access",
            project_id=project_id,
            target_user_id=user_id,
            result="success"
        )
        
        logger.info(
            "access_revoked",
            user_id=user_id,
            project_id=project_id,
            revoked_by=revoked_by,
            existed=bool(deleted)
        )
        
        return bool(deleted)
    
    async def get_user_projects(self, user_id: str) -> List[str]:
        """
        Get all projects a user has access to.
        
        Args:
            user_id: User identifier
        
        Returns:
            List of project IDs
        """
        pattern = f"access:grant:{user_id}:*"
        keys = []
        
        # Scan Redis for matching keys
        async for key in self.redis_client.scan_iter(match=pattern):
            # Extract project_id from key
            # Key format: access:grant:{user_id}:{project_id}
            parts = key.split(":")
            if len(parts) == 4:
                keys.append(parts[3])
        
        logger.debug("user_projects_retrieved", user_id=user_id, count=len(keys))
        
        return keys
    
    async def get_project_users(self, project_id: str) -> List[Dict]:
        """
        Get all users with access to a project.
        
        Args:
            project_id: Project identifier
        
        Returns:
            List of dicts with user_id and role
        """
        pattern = f"access:grant:*:{project_id}"
        users = []
        
        # Scan Redis for matching keys
        async for key in self.redis_client.scan_iter(match=pattern):
            grant_data = await self.redis_client.get(key)
            if grant_data:
                grant_dict = json.loads(grant_data)
                users.append({
                    "user_id": grant_dict["user_id"],
                    "role": grant_dict["role"],
                    "granted_at": grant_dict["granted_at"]
                })
        
        logger.debug("project_users_retrieved", project_id=project_id, count=len(users))
        
        return users
    
    # ========================================================================
    # PERMISSION CHECKING (FAST PATH)
    # ========================================================================
    
    async def can_access(self, user_id: str, project_id: str) -> bool:
        """
        Check if user has ANY access to project.
        
        Fast path for basic access checks.
        
        Args:
            user_id: User identifier
            project_id: Project identifier
        
        Returns:
            True if user has any role on project
        """
        grant = await self._get_grant(user_id, project_id)
        return grant is not None
    
    def can_read(self, user_id: str, project_id: str) -> bool:
        """
        Check if user can read from project (synchronous, uses cache).
        
        Args:
            user_id: User identifier
            project_id: Project identifier
        
        Returns:
            True if user has read permission
        """
        # Try memory cache first (no async needed)
        cache_key = f"{user_id}:{project_id}"
        
        if cache_key in self._memory_cache:
            timestamp = self._cache_timestamps.get(cache_key)
            if timestamp and (datetime.now() - timestamp).seconds < self.cache_ttl:
                grant = self._memory_cache[cache_key]
                return Permission.READ_DATA in ROLE_PERMISSIONS[grant.role]
        
        # Cache miss - return False and let caller use async version
        return False
    
    async def can_write(self, user_id: str, project_id: str) -> bool:
        """
        Check if user can write to project.
        
        Args:
            user_id: User identifier
            project_id: Project identifier
        
        Returns:
            True if user has write permission
        """
        return await self.has_permission(user_id, project_id, Permission.WRITE_DATA)
    
    async def can_delete(self, user_id: str, project_id: str) -> bool:
        """
        Check if user can delete from project.
        
        Args:
            user_id: User identifier
            project_id: Project identifier
        
        Returns:
            True if user has delete permission
        """
        return await self.has_permission(user_id, project_id, Permission.DELETE_DATA)
    
    async def can_manage_users(self, user_id: str, project_id: str) -> bool:
        """
        Check if user can manage other users' access.
        
        Args:
            user_id: User identifier
            project_id: Project identifier
        
        Returns:
            True if user has grant/revoke permissions
        """
        return await self.has_permission(user_id, project_id, Permission.GRANT_ACCESS)
    
    async def has_permission(
        self,
        user_id: str,
        project_id: str,
        permission: Permission
    ) -> bool:
        """
        Check if user has specific permission on project.
        
        Core permission checking logic.
        
        Args:
            user_id: User identifier
            project_id: Project identifier
            permission: Permission to check
        
        Returns:
            True if user has the permission
        """
        grant = await self._get_grant(user_id, project_id)
        
        if not grant:
            return False
        
        # Check if grant has expired
        if grant.expires_at and datetime.now() > grant.expires_at:
            logger.warning("expired_grant_accessed", user_id=user_id, project_id=project_id)
            return False
        
        # Check role permissions
        role_perms = ROLE_PERMISSIONS.get(grant.role, set())
        has_perm = permission in role_perms
        
        logger.debug(
            "permission_checked",
            user_id=user_id,
            project_id=project_id,
            permission=permission.value,
            role=grant.role.value,
            result=has_perm
        )
        
        return has_perm
    
    async def get_user_role(self, user_id: str, project_id: str) -> Optional[str]:
        """
        Get user's role on project.
        
        Args:
            user_id: User identifier
            project_id: Project identifier
        
        Returns:
            Role name (admin/editor/viewer) or None
        """
        grant = await self._get_grant(user_id, project_id)
        return grant.role.value if grant else None
    
    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================
    
    def _grant_key(self, user_id: str, project_id: str) -> str:
        """Generate Redis key for access grant."""
        return f"access:grant:{user_id}:{project_id}"
    
    def _audit_key(self) -> str:
        """Generate Redis key for audit log."""
        return "access:audit_log"
    
    async def _store_grant(self, grant: AccessGrant):
        """Store access grant in Redis."""
        key = self._grant_key(grant.user_id, grant.project_id)
        
        grant_dict = {
            "user_id": grant.user_id,
            "project_id": grant.project_id,
            "role": grant.role.value,
            "granted_by": grant.granted_by,
            "granted_at": grant.granted_at.isoformat(),
            "expires_at": grant.expires_at.isoformat() if grant.expires_at else None
        }
        
        await self.redis_client.set(
            key,
            json.dumps(grant_dict),
            ex=self.cache_ttl if not grant.expires_at else None
        )
    
    async def _get_grant(self, user_id: str, project_id: str) -> Optional[AccessGrant]:
        """
        Retrieve access grant with caching.
        
        Checks:
        1. In-memory cache (instant)
        2. Redis (fast)
        3. Returns None if not found
        """
        cache_key = f"{user_id}:{project_id}"
        
        # Check memory cache
        if cache_key in self._memory_cache:
            timestamp = self._cache_timestamps.get(cache_key)
            if timestamp and (datetime.now() - timestamp).seconds < self.cache_ttl:
                return self._memory_cache[cache_key]
        
        # Check Redis
        key = self._grant_key(user_id, project_id)
        grant_data = await self.redis_client.get(key)
        
        if not grant_data:
            return None
        
        # Parse grant
        grant_dict = json.loads(grant_data)
        grant = AccessGrant(
            user_id=grant_dict["user_id"],
            project_id=grant_dict["project_id"],
            role=Role(grant_dict["role"]),
            granted_by=grant_dict["granted_by"],
            granted_at=datetime.fromisoformat(grant_dict["granted_at"]),
            expires_at=datetime.fromisoformat(grant_dict["expires_at"]) if grant_dict["expires_at"] else None
        )
        
        # Update memory cache
        self._memory_cache[cache_key] = grant
        self._cache_timestamps[cache_key] = datetime.now()
        
        return grant
    
    def _invalidate_cache(self, user_id: str, project_id: str):
        """Invalidate memory cache for user/project."""
        cache_key = f"{user_id}:{project_id}"
        self._memory_cache.pop(cache_key, None)
        self._cache_timestamps.pop(cache_key, None)
    
    async def _audit_log(
        self,
        user_id: str,
        action: str,
        project_id: str,
        target_user_id: Optional[str] = None,
        result: Literal["success", "denied"] = "success",
        details: Dict = None
    ):
        """Log access control event."""
        if not self.enable_audit_log:
            return
        
        entry = AuditLogEntry(
            timestamp=datetime.now(),
            user_id=user_id,
            action=action,
            project_id=project_id,
            target_user_id=target_user_id,
            result=result,
            details=details or {}
        )
        
        # Store in Redis list (LPUSH for newest first)
        audit_key = self._audit_key()
        entry_json = json.dumps({
            "timestamp": entry.timestamp.isoformat(),
            "user_id": entry.user_id,
            "action": entry.action,
            "project_id": entry.project_id,
            "target_user_id": entry.target_user_id,
            "result": entry.result,
            "details": entry.details
        })
        
        await self.redis_client.lpush(audit_key, entry_json)
        
        # Trim to last 1000 entries
        await self.redis_client.ltrim(audit_key, 0, 999)
        
        logger.info(
            "access_audit",
            user_id=user_id,
            action=action,
            project_id=project_id,
            result=result
        )
    
    async def get_audit_log(
        self,
        user_id: str,
        limit: int = 100,
        project_id: Optional[str] = None
    ) -> List[AuditLogEntry]:
        """
        Retrieve audit log entries.
        
        Args:
            user_id: User requesting the log (must have VIEW_AUDIT_LOG permission)
            limit: Maximum number of entries to return
            project_id: Optional project filter
        
        Returns:
            List of AuditLogEntry objects
        
        Raises:
            PermissionError: If user lacks permission
        """
        # Check permission (any project where user is admin)
        if project_id:
            if not await self.has_permission(user_id, project_id, Permission.VIEW_AUDIT_LOG):
                raise PermissionError(f"User {user_id} cannot view audit log")
        
        # Retrieve from Redis
        audit_key = self._audit_key()
        entries_json = await self.redis_client.lrange(audit_key, 0, limit - 1)
        
        entries = []
        for entry_json in entries_json:
            entry_dict = json.loads(entry_json)
            
            # Filter by project if specified
            if project_id and entry_dict["project_id"] != project_id:
                continue
            
            entry = AuditLogEntry(
                timestamp=datetime.fromisoformat(entry_dict["timestamp"]),
                user_id=entry_dict["user_id"],
                action=entry_dict["action"],
                project_id=entry_dict["project_id"],
                target_user_id=entry_dict.get("target_user_id"),
                result=entry_dict["result"],
                details=entry_dict.get("details", {})
            )
            entries.append(entry)
        
        logger.debug("audit_log_retrieved", user_id=user_id, count=len(entries))
        
        return entries


# Convenience function for orchestrator
async def check_project_access(
    user_id: str,
    project_id: str,
    access_control: AccessControl
) -> bool:
    """
    Quick access check helper.
    
    Args:
        user_id: User identifier
        project_id: Project identifier
        access_control: AccessControl instance
    
    Returns:
        True if user has any access to project
    
    Example:
        if await check_project_access("user123", "client_acme", ac):
            # Proceed with operation
            pass
    """
    return await access_control.can_access(user_id, project_id)
