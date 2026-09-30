"""API dependencies."""

from app.api.deps.auth import consultant_auth_enabled, require_consultant

__all__ = ["consultant_auth_enabled", "require_consultant"]
