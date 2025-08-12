"""Plugin base interfaces for pipeline extension.

Lightweight abstraction so future external packages can register steps
without directly editing core pipeline module.

Current usage: internal only; external discovery can later look for
entry points named 'ecfr_scraper.plugins'.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any, Dict


class PipelinePlugin(Protocol):  # pragma: no cover - protocol definition
    name: str
    version: str

    def register(self, registry: Dict[str, Any]) -> None:
        """Register step callables into provided registry."""
        ...


@dataclass
class Instruction:
    """Structured instruction model (placeholder for future LLM / DSL use)."""
    action: str
    target: str | None = None
    params: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            'action': self.action,
            'target': self.target,
            'params': self.params,
        }.items() if v is not None}


def load_entrypoint_plugins():  # pragma: no cover - dynamic loading placeholder
    """Future: iterate pkg entry points and auto-register plugins."""
    return []
