"""
Base exception types for the project.

Subclass ProjectError or use exception_factory() to add new exception types
on demand. All exceptions carry a machine-readable code and optional HTTP
status for API layers.
"""
from __future__ import annotations

import traceback
from typing import Any, Optional, Type


class ProjectError(Exception):
    """
    Base exception for all project errors.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable slug (defaults to class __name__).
        http_status: Suggested HTTP status for API responses (default 500).
        details: Optional dict for extra context (e.g. validation errors).
        cause: Optional chained exception.
    """

    default_code: str = "ERROR"
    default_http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        http_status: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else getattr(
            self.__class__, "default_code", self.__class__.__name__
        )
        self.http_status = (
            http_status
            if http_status is not None
            else getattr(self.__class__, "default_http_status", 500)
        )
        self.details: dict[str, Any] = details or {}
        self.cause = cause

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, code={self.code!r}, "
            f"http_status={self.http_status})"
        )

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging or API responses."""
        out: dict[str, Any] = {
            "message": self.message,
            "code": self.code,
            "http_status": self.http_status,
        }
        if self.details:
            out["details"] = self.details
        if self.cause is not None:
            out["cause"] = str(self.cause)
            out["cause_traceback"] = traceback.format_exception(
                type(self.cause), self.cause, self.cause.__traceback__
            )
        return out


def exception_factory(
    name: str,
    *,
    code: Optional[str] = None,
    http_status: int = 500,
    base: Type[ProjectError] = ProjectError,
) -> Type[ProjectError]:
    """
    Create a new exception class on demand.

    Example:
        ValidationError = exception_factory("ValidationError", code="VALIDATION_ERROR", http_status=400)
        raise ValidationError("Invalid email format", details={"field": "email"})
    """
    code = code or name.upper().replace(" ", "_")
    return type(
        name,
        (base,),
        {
            "default_code": code,
            "default_http_status": http_status,
        },
    )
