"""运行时状态对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.contracts.message import ChatMessage
from app.contracts.tool import ToolResult
from app.contracts.trace import TraceEvent

AgentStatus = Literal["running", "completed", "partial_completed", "failed", "max_steps_exceeded"]


@dataclass
class AgentState:
    """最小 Agent 循环中的可变状态。

    使用 dataclass 而非 Pydantic BaseModel，因为 AgentState 在循环中
    被频繁原地修改（step_count += 1、messages.append 等），
    dataclass 的可变语义更符合实际使用方式。
    """

    run_id: str
    session_id: str
    task: str
    # 运行时快照中保留 max_steps，便于排查无限循环、trace 观察和状态展示。
    # 真正的执行约束仍由 RunContext 提供。
    max_steps: int = 3
    messages: list[ChatMessage] = field(default_factory=list)
    history_message_count: int = 0
    step_count: int = 0
    status: AgentStatus = "running"
    final_output: str = ""
    llm_call_count: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    memory_write_count: int = 0
    fallback_count: int = 0
    trace_events: list[TraceEvent] = field(default_factory=list)
    last_successful_tool_result: ToolResult | None = None

    @property
    def is_finished(self) -> bool:
        """返回当前任务是否已经结束。"""

        return self.status != "running"

    @property
    def is_completed(self) -> bool:
        """返回当前任务是否已成功完成。"""

        return self.status in {"completed", "partial_completed"}
