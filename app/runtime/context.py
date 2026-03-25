"""运行时上下文对象。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.llm.client import LLMProvider
from app.memory.session_memory import SessionMemory
from app.memory.summary_memory import SummaryMemory
from app.tools.registry import ToolRegistry

TOOL_ERROR_GUIDANCE = """
Tool-use policy:
- Tool results are returned as JSON-like text.
- If a tool result contains `"ok": false` or `ok=false`, treat it as a tool failure signal.
- Before retrying, diagnose the failure from the error payload and explain the cause briefly in your reasoning.
- Retry only if you can fix the tool name, arguments, or strategy with high confidence.
- If the failure is not recoverable, stop using that tool path and give the user a clear answer or ask for missing information.
- Do not repeat the same failing tool call with identical arguments.
""".strip()


class RunContext(BaseModel):
    """单次 Agent 运行的执行上下文。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    run_id: str
    session_id: str
    provider: LLMProvider
    model: str
    tool_registry: ToolRegistry
    session_memory: SessionMemory
    summary_memory: SummaryMemory
    system_prompt: str = "You are a helpful assistant."
    temperature: float = 0.0
    max_steps: int = 3

    @property
    def effective_system_prompt(self) -> str:
        """将调用方系统提示与运行时工具规则合并。"""
        return f"{self.system_prompt}\n\n{TOOL_ERROR_GUIDANCE}"
