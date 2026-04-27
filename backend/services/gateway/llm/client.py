from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Minimal contract for config-generating LLM backends."""

    def generate(self, system: str, user: str) -> str:
        ...
