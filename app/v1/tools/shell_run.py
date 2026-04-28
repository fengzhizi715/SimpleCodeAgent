"""Shell 执行工具。"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from app.contracts.tool import ToolDefinition, ToolResult
from app.core.exceptions import AppError
from app.core.logger import get_logger
from app.v1.tools.base import Tool

logger = get_logger(__name__)

ALLOWED_EXECUTABLES = {
    "python",
    "python3",
    "pytest",
    "ls",
    "pwd",
    "rg",
    "git",
    "gradle",
    "./gradlew",
    "cmake",
    "ctest",
    "make",
    "codex",
    "cursor",
    "cursor-agent",
    ".venv/bin/python",
}

BLOCKED_EXECUTABLES = {
    "rm",
    "curl",
    "wget",
    "sudo",
    "chmod",
    "chown",
    "mkfs",
    "dd",
    "scp",
    "ssh",
    "nc",
    "netcat",
    "telnet",
    "kill",
    "pkill",
    "killall",
    "reboot",
    "shutdown",
    "systemctl",
    "launchctl",
}

BLOCKED_GIT_SUBCOMMANDS = {
    "push",
    "reset",
    "clean",
    "checkout",
    "restore",
    "rebase",
    "merge",
    "commit",
    "cherry-pick",
}

SAFE_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "rev-parse",
}


class ShellRunTool(Tool):
    """在工作区内执行 Shell 命令。"""

    DEFAULT_MAX_OUTPUT_CHARS = 10_000

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
                    "max_output_chars": {
                        "type": "integer",
                        "description": "Maximum number of characters preserved for stdout and stderr.",
                        "default": self.DEFAULT_MAX_OUTPUT_CHARS,
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
        max_output_chars = int(arguments.get("max_output_chars", self.DEFAULT_MAX_OUTPUT_CHARS))
        if not command:
            return self.error(tool_call_id=tool_call_id, message="Command must not be empty.")
        parsed_command = self._parse_command(command, tool_call_id=tool_call_id)
        if isinstance(parsed_command, ToolResult):
            return parsed_command
        command_argv = parsed_command

        workdir = self.resolve_path(raw_workdir)
        if not workdir.exists() or not workdir.is_dir():
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Workdir does not exist or is not a directory: {raw_workdir}",
                workdir=str(workdir),
            )

        try:
            logger.info(
                "Running shell command: command=%s workdir=%s timeout=%ss",
                command,
                workdir,
                timeout,
            )
            exe0 = command_argv[0]
            # External coding CLIs are often missing when the IDE shell PATH differs from uvicorn's.
            if exe0 in {"cursor", "cursor-agent", "codex"} and shutil.which(exe0) is None:
                return self.error(
                    tool_call_id=tool_call_id,
                    message=(
                        f"Executable not found in PATH: {exe0}. "
                        "Install the shell command from the app, or set CURSOR_CLI_PATH / CODEX_CLI_PATH "
                        "to the full binary path (API field cursor_cli_path / codex_cli_path also supported)."
                    ),
                    command=command,
                    workdir=str(workdir),
                )
            completed = subprocess.run(
                command_argv,
                cwd=workdir,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            if completed.returncode == 0:
                logger.info("Shell command completed: exit_code=%s command=%s", completed.returncode, command)
            else:
                logger.error("Shell command failed: exit_code=%s command=%s", completed.returncode, command)
            stdout, stdout_truncated = self._truncate_output(completed.stdout, max_output_chars)
            stderr, stderr_truncated = self._truncate_output(completed.stderr, max_output_chars)
            return self.success(
                tool_call_id=tool_call_id,
                content={
                    "ok": completed.returncode == 0,
                    "command": command,
                    "workdir": str(workdir),
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "exit_code": completed.returncode,
                    "timed_out": False,
                },
            )
        except FileNotFoundError as exc:
            hint = ""
            name = Path(command_argv[0]).name
            if name in {"cursor", "cursor-agent", "codex"}:
                hint = (
                    " Set CURSOR_CLI_PATH or CODEX_CLI_PATH to the full path of the CLI binary, "
                    "or install the shell command from the Cursor/Codex app."
                )
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Executable not found: {command_argv[0]}.{hint}",
                command=command,
                workdir=str(workdir),
                detail=str(exc),
            )
        except subprocess.TimeoutExpired as exc:
            logger.error("Shell command timed out: timeout=%ss command=%s", timeout, command)
            stdout, stdout_truncated = self._truncate_output(exc.stdout or "", max_output_chars)
            stderr, stderr_truncated = self._truncate_output(exc.stderr or "", max_output_chars)
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Command timed out after {timeout} seconds.",
                command=command,
                workdir=str(workdir),
                stdout=stdout,
                stderr=stderr,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                exit_code=None,
                timed_out=True,
            )

    def _parse_command(self, command: str, *, tool_call_id: str) -> list[str] | ToolResult:
        """解析并校验 shell 命令，限制为验证类命令。"""
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Command parse failed: {exc}",
                command=command,
            )
        if not argv:
            return self.error(
                tool_call_id=tool_call_id,
                message="Command must not be empty.",
                command=command,
            )
        executable = argv[0]
        executable_name = Path(executable).name
        if executable in BLOCKED_EXECUTABLES or executable_name in BLOCKED_EXECUTABLES:
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Blocked command: {executable}",
                command=command,
            )
        if executable not in ALLOWED_EXECUTABLES and executable_name not in ALLOWED_EXECUTABLES:
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Command is not allowed: {executable}",
                command=command,
            )
        if executable_name == "git" and len(argv) > 1 and argv[1] in BLOCKED_GIT_SUBCOMMANDS:
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Blocked git subcommand: {argv[1]}",
                command=command,
            )
        if executable_name == "git" and len(argv) > 1 and argv[1] not in SAFE_GIT_SUBCOMMANDS:
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Git subcommand is not allowed: {argv[1]}",
                command=command,
            )
        validation_error = self._validate_command_arguments(argv, command, tool_call_id=tool_call_id)
        if validation_error is not None:
            return validation_error
        return argv

    def _validate_command_arguments(
        self,
        argv: list[str],
        command: str,
        *,
        tool_call_id: str,
    ) -> ToolResult | None:
        """校验命令参数，避免通过绝对路径或解释器内联脚本绕出工作区。"""
        executable_name = Path(argv[0]).name

        if executable_name in {"python", "python3"}:
            if any(arg == "-c" or arg.startswith("-c") for arg in argv[1:]):
                return self.error(
                    tool_call_id=tool_call_id,
                    message="Inline Python execution via -c is not allowed.",
                    command=command,
                )
        if argv[0] == ".venv/bin/python" and any(arg == "-c" or arg.startswith("-c") for arg in argv[1:]):
            return self.error(
                tool_call_id=tool_call_id,
                message="Inline Python execution via -c is not allowed.",
                command=command,
            )

        for arg in argv[1:]:
            if not arg or arg.startswith("-"):
                continue
            if arg == ".":
                continue
            if self._looks_like_non_path_argument(executable_name, arg):
                continue
            if Path(arg).is_absolute():
                try:
                    self.resolve_path(arg)
                except AppError:
                    return self.error(
                        tool_call_id=tool_call_id,
                        message=f"Path argument is outside workspace: {arg}",
                        command=command,
                    )
                continue
            if "/" in arg or arg.startswith("."):
                try:
                    self.resolve_path(arg)
                except AppError:
                    return self.error(
                        tool_call_id=tool_call_id,
                        message=f"Path argument is outside workspace: {arg}",
                        command=command,
                    )
        return None

    def _looks_like_non_path_argument(self, executable_name: str, arg: str) -> bool:
        """判断参数更像关键词/模式而非路径，避免误拦合法验证命令。"""
        if executable_name in {"pytest", "python", "python3", ".venv/bin/python"}:
            return False
        if executable_name == "rg":
            return "/" not in arg and "." not in arg
        if executable_name == "git":
            return True
        return "/" not in arg and "." not in arg

    def _truncate_output(self, value: str, max_chars: int) -> tuple[str, bool]:
        """截断 stdout/stderr，避免大输出撑爆 trace。"""
        if max_chars <= 0:
            return "", bool(value)
        if len(value) <= max_chars:
            return value, False
        return value[:max_chars], True
