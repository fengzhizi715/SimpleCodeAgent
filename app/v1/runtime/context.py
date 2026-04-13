"""运行时上下文对象。"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(kw_only=True)
class RunContext:
    """单次 Agent 运行的执行上下文。

    使用 dataclass 而非 Pydantic BaseModel，因为 RunContext 持有
    LLMProvider、ToolRegistry 等不可序列化的运行时对象，
    Pydantic 的校验和序列化能力在此场景下无法发挥作用。

    kw_only=True 允许必填字段和有默认值的字段混合声明，
    所有字段都必须通过关键字参数传入，避免位置参数顺序问题。
    """

    run_id: str
    root_run_id: str
    session_id: str
    parent_run_id: str | None = None
    provider: LLMProvider
    model: str
    reasoning_mode: str = "default"
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
