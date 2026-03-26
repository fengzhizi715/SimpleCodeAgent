"""运行时状态对象。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.message import Message
from app.contracts.trace import TraceEvent

AgentStatus = Literal["running", "completed", "failed", "max_steps_exceeded"]


class AgentState(BaseModel):
    """最小 Agent 循环中的可变状态。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    task: str
    messages: list[Message] = Field(default_factory=list)
    history_message_count: int = 0
    step_count: int = 0
    status: AgentStatus = "running"
    final_output: str = ""
    trace_events: list[TraceEvent] = Field(default_factory=list)
