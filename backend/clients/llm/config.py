from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


@dataclass
class LLMConfig:
    """Base configuration class for LLM instances."""
    
    # Required fields
    model: str
    provider: Optional[str] = None  # Made optional for flexibility
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    
    # Optional fields
    organization: Optional[str] = None
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: float = 60.0
    max_retries: int = 3
    
    # Provider-specific and management fields
    extra: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    name: Optional[str] = None
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary, filtering out None values."""
        config_dict = asdict(self)
        # Remove None values for cleaner config
        return {k: v for k, v in config_dict.items() if v is not None}