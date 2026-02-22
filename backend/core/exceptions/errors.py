"""
Built-in exception types. Add new ones here or via exception_factory().
"""
from __future__ import annotations

from backend.core.exceptions.base import ProjectError


class ConfigurationError(ProjectError):
    """Invalid or missing configuration."""

    default_code = "CONFIGURATION_ERROR"
    default_http_status = 500


class ValidationError(ProjectError):
    """Request or input validation failed."""

    default_code = "VALIDATION_ERROR"
    default_http_status = 400


class NotFoundError(ProjectError):
    """Requested resource not found."""

    default_code = "NOT_FOUND"
    default_http_status = 404


class UnauthorizedError(ProjectError):
    """Authentication required or failed."""

    default_code = "UNAUTHORIZED"
    default_http_status = 401


class ForbiddenError(ProjectError):
    """Access to resource is forbidden."""

    default_code = "FORBIDDEN"
    default_http_status = 403


class ConflictError(ProjectError):
    """Resource state conflict (e.g. duplicate, version mismatch)."""

    default_code = "CONFLICT"
    default_http_status = 409


class ExternalServiceError(ProjectError):
    """External service (LLM, DB, storage) failed."""

    default_code = "EXTERNAL_SERVICE_ERROR"
    default_http_status = 502


class RateLimitError(ProjectError):
    """Rate limit exceeded."""

    default_code = "RATE_LIMIT"
    default_http_status = 429


class UnsupportedFileTypeError(ProjectError):
    """File type not supported or no parser registered."""

    default_code = "UNSUPPORTED_FILE_TYPE"
    default_http_status = 400


class ExtractionError(ProjectError):
    """Text extraction failed (read/parse error)."""

    default_code = "EXTRACTION_ERROR"
    default_http_status = 422


class VectorstoreError(ProjectError):
    """Vector database (Qdrant) operation failed."""

    default_code = "VECTORSTORE_ERROR"
    default_http_status = 502
