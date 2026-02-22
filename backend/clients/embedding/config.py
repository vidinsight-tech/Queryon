"""Embedding client configuration."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class EmbeddingConfig:
    """Configuration for an embedding client instance."""

    model: str
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    # Optional
    timeout: float = 60.0
    max_retries: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    name: Optional[str] = None
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, omitting None values."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}
