"""运行时上下文对象。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.tools.registry import ToolRegistry

TOOL_ERROR_GUIDANCE = """
Tool-use policy:
- Tool results are returned as JSON-like text.
- If a tool result contains `"ok": false` or `ok=false`, treat it as a tool failure signal.
- Before retrying, diagnose the failure from the error payload and explain the cause briefly in your reasoning.
- Retry only if you can fix the tool name, arguments, or strategy with high confidence.
- If the failure is not recoverable, stop using that tool path and give the user a clear answer or ask for missing information.
- Do not repeat the same failing tool call with identical arguments.
""".strip()

CODING_WORKFLOW_GUIDANCE = """
Coding-task policy:
- For code generation, imitation, CRUD changes, and bug fixes, prefer a bounded workflow: inspect -> edit -> verify.
- Inspect existing code first with `file_search`, `read_file`, and `retrieve_docs` before writing.
- Keep edits local and minimal. Avoid broad refactors unless the task explicitly requires them.
- When creating a new module, follow nearby naming, structure, and style patterns.
- After changing code, verify with `shell_run` using a narrow command such as `pytest`, `python -m`, or `py_compile`.
- If verification fails, diagnose the failure, apply a focused fix, and verify again.
- In your final answer, summarize what changed and how it was verified.
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
    trace_recorder: JsonlTraceRecorder
    trace_repository: SQLiteTraceRepository
    system_prompt: str = "You are a helpful assistant."
    temperature: float = 0.0
    max_steps: int = 3
    run_timeout_seconds: int = 120
    persist_session_memory: bool = True

    @property
    def effective_system_prompt(self) -> str:
        """将调用方系统提示与运行时工具规则合并。"""
        return (
            f"{self.system_prompt}\n\n"
            f"{TOOL_ERROR_GUIDANCE}\n\n"
            f"{CODING_WORKFLOW_GUIDANCE}"
        )
