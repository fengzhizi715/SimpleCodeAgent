"""运行时状态对象。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.message import ChatMessage
from app.contracts.trace import TraceEvent

AgentStatus = Literal["running", "completed", "failed", "max_steps_exceeded"]


class AgentState(BaseModel):
    """最小 Agent 循环中的可变状态。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    task: str
    # 运行时快照中保留 max_steps，便于排查无限循环、trace 观察和状态展示。
    # 真正的执行约束仍由 RunContext 提供。
    max_steps: int = 3
    messages: list[ChatMessage] = Field(default_factory=list)
    history_message_count: int = 0
    step_count: int = 0
    status: AgentStatus = "running"
    final_output: str = ""
    llm_call_count: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    memory_write_count: int = 0
    fallback_count: int = 0
    trace_events: list[TraceEvent] = Field(default_factory=list)
