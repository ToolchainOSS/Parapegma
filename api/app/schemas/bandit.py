"""Bandit arm configuration schema for context prefetch gates."""

from __future__ import annotations

from pydantic import BaseModel


class ArmConfig(BaseModel):
    """Feature gates for memory/rag/web retrieval arms."""

    arm_id: str
    use_memory: bool
    use_rag: bool
    use_web: bool
