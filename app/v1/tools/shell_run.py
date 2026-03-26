"""Shell 执行工具。"""

from __future__ import annotations

import subprocess

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


class ShellRunTool(Tool):
    """在工作区内执行 Shell 命令。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell_run",
            description="Run a shell command in a workspace directory and return stdout, stderr, and exit code.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                    "workdir": {
                        "type": "string",
                        "description": "Optional working directory inside the workspace.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Command timeout in seconds.",
                        "default": 20,
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        command = str(arguments.get("command", "")).strip()
        raw_workdir = str(arguments.get("workdir", ".")).strip() or "."
        timeout = int(arguments.get("timeout", 20))
        if not command:
            return self.error(tool_call_id=tool_call_id, message="Command must not be empty.")

        workdir = self.resolve_path(raw_workdir)
        if not workdir.exists() or not workdir.is_dir():
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Workdir does not exist or is not a directory: {raw_workdir}",
                workdir=str(workdir),
            )

        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            return self.success(
                tool_call_id=tool_call_id,
                content={
                    "ok": completed.returncode == 0,
                    "command": command,
                    "workdir": str(workdir),
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "exit_code": completed.returncode,
                    "timed_out": False,
                },
            )
        except subprocess.TimeoutExpired as exc:
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Command timed out after {timeout} seconds.",
                command=command,
                workdir=str(workdir),
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                exit_code=None,
                timed_out=True,
            )
