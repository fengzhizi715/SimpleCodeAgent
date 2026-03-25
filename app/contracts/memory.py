"""Memory 协议定义。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class MemoryEntry(BaseModel):
    """供后续 Agent 运行使用的持久化记忆项。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    key: str
    value: str
    kind: str = "note"
    metadata: dict[str, Any] = Field(default_factory=dict)
