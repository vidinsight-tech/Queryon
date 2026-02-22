"""
Project exception system.

Usage:
    from backend.core.exceptions import ProjectError, ValidationError, exception_factory

    # Built-in types
    raise ValidationError("Invalid input", details={"field": "email"})

    # Add new type on demand
    IngestionError = exception_factory("IngestionError", code="INGESTION_ERROR", http_status=422)
    raise IngestionError("Failed to parse file", cause=original_error)
"""
from backend.core.exceptions.base import ProjectError, exception_factory
from backend.core.exceptions.errors import (
    ConfigurationError,
    ConflictError,
    ExternalServiceError,
    ExtractionError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    UnauthorizedError,
    UnsupportedFileTypeError,
    ValidationError,
    VectorstoreError,
)

__all__ = [
    "ProjectError",
    "exception_factory",
    "ConfigurationError",
    "ValidationError",
    "NotFoundError",
    "UnauthorizedError",
    "ForbiddenError",
    "ConflictError",
    "ExternalServiceError",
    "RateLimitError",
    "UnsupportedFileTypeError",
    "ExtractionError",
    "VectorstoreError",
]
