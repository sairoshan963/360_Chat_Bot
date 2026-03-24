from abc import ABC, abstractmethod
import uuid as _uuid_mod
from django.db import connection


def db_uuid(value) -> str:
    """
    Return a UUID value in the format expected by the current database backend.

    PostgreSQL stores UUIDs natively (accepts standard hyphenated string).
    SQLite stores UUIDs as CHAR(32) — 32 hex characters WITHOUT hyphens.

    Using this helper in raw SQL parameters ensures cross-database compatibility
    so that unit tests (SQLite) and production (PostgreSQL) behave identically.
    """
    uid = value if isinstance(value, _uuid_mod.UUID) else _uuid_mod.UUID(str(value))
    if connection.vendor == 'sqlite':
        return uid.hex  # 32-char hex, no hyphens — matches SQLite CHAR(32) storage
    return str(uid)    # Standard hyphenated form — accepted by PostgreSQL UUID type


class BaseCommand(ABC):
    """Abstract base class for all chat command handlers."""

    # Roles allowed to execute this command
    allowed_roles: list[str] = []

    # Required parameters for this command
    required_params: list[str] = []

    # Whether this command requires user confirmation before execution
    requires_confirmation: bool = False

    @abstractmethod
    def execute(self, parameters: dict, user) -> dict:
        """
        Execute the command.
        Returns: {"success": bool, "message": str, "data": dict}
        """
        pass

    def validate_params(self, parameters: dict) -> list[str]:
        """Returns list of missing required parameters."""
        return [p for p in self.required_params if not parameters.get(p)]

    def check_permission(self, user) -> bool:
        """Check if user role is allowed to run this command."""
        if not self.allowed_roles:
            return True
        return getattr(user, 'role', None) in self.allowed_roles
