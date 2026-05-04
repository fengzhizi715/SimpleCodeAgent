"""Safe external coding command template builder."""

from __future__ import annotations

import os
import re
import shlex
import shutil
from pathlib import Path

DEFAULT_EXTERNAL_TEMPLATES: dict[str, str] = {
    "codex_cli": "codex exec --sandbox workspace-write {prompt}",
    # 多数安装使用独立命令 cursor-agent（也可用模板改成 cursor agent …）
    "cursor_cli": "cursor-agent --trust {prompt}",
}

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_ALLOWED_PLACEHOLDERS = {"prompt", "workdir"}


def _quote_template_arg(arg: str) -> str:
    """Quote normal args while leaving placeholders for the final replacement pass."""
    if arg in {"{prompt}", "{workdir}"}:
        return arg
    return shlex.quote(arg)


def _resolve_external_binary(agent_key: str, policy: dict[str, object] | None) -> str:
    """Resolve Codex/Cursor binary: explicit path → env → PATH → default name."""
    policy = policy or {}
    if agent_key == "cursor_cli":
        for raw in (
            str(policy.get("cursor_cli_path") or "").strip(),
            (os.getenv("CURSOR_CLI_PATH") or "").strip(),
        ):
            if raw:
                p = Path(raw).expanduser()
                if p.is_file() and os.access(p, os.X_OK):
                    return str(p.resolve())
        found = shutil.which("cursor-agent") or shutil.which("cursor")
        return found if found else "cursor-agent"
    if agent_key == "codex_cli":
        for raw in (
            str(policy.get("codex_cli_path") or "").strip(),
            (os.getenv("CODEX_CLI_PATH") or "").strip(),
        ):
            if raw:
                p = Path(raw).expanduser()
                if p.is_file() and os.access(p, os.X_OK):
                    return str(p.resolve())
        found = shutil.which("codex")
        return found if found else "codex"
    return "cursor-agent"


def _inject_resolved_executable(template: str, agent_key: str, policy: dict[str, object] | None) -> str:
    """Replace the leading CLI token (cursor-agent / cursor / codex) with the resolved absolute path when applicable."""
    resolved = _resolve_external_binary(agent_key, policy)
    lead_ws_len = len(template) - len(template.lstrip())
    lead_ws = template[:lead_ws_len]
    rest = template[lead_ws_len:]
    parts = rest.split(None, 1)
    if not parts:
        return template
    first = parts[0]
    tail = rest[len(first) :]
    name = Path(first).name
    if agent_key == "cursor_cli" and name not in {"cursor", "cursor-agent"}:
        return template
    if agent_key == "codex_cli" and name != "codex":
        return template
    quoted = shlex.quote(resolved)
    return f"{lead_ws}{quoted}{tail}"


def _ensure_cursor_trust_flag(template: str, agent_key: str) -> str:
    """Cursor Agent 在后端非交互运行时必须显式信任 workspace。"""
    if agent_key != "cursor_cli":
        return template
    try:
        argv = shlex.split(template)
    except ValueError:
        return template
    if not argv:
        return template
    if any(arg in {"--trust", "--yolo", "-f"} for arg in argv[1:]):
        return template

    executable = argv[0]
    executable_name = Path(executable).name
    if executable_name == "cursor-agent":
        return f"{shlex.quote(executable)} --trust {' '.join(_quote_template_arg(arg) for arg in argv[1:])}".strip()
    if executable_name == "cursor" and len(argv) > 1 and argv[1] == "agent":
        tail = " ".join(_quote_template_arg(arg) for arg in argv[2:])
        return f"{shlex.quote(executable)} agent --trust {tail}".strip()
    return template


def _ensure_codex_workspace_write_flag(template: str, agent_key: str) -> str:
    """Codex exec 默认 read-only；外部编码执行器需要 workspace-write 才能落盘补丁。"""
    if agent_key != "codex_cli":
        return template
    try:
        argv = shlex.split(template)
    except ValueError:
        return template
    if len(argv) < 2:
        return template
    executable_name = Path(argv[0]).name
    if executable_name != "codex" or argv[1] != "exec":
        return template
    explicit_sandbox = any(
        arg in {"--sandbox", "-s", "--full-auto", "--dangerously-bypass-approvals-and-sandbox"}
        for arg in argv[2:]
    )
    if explicit_sandbox:
        return template
    rebuilt = [argv[0], argv[1], "--sandbox", "workspace-write", *argv[2:]]
    return " ".join(_quote_template_arg(arg) for arg in rebuilt)


def build_external_command_from_template(
    *,
    external_agent: str,
    prompt: str,
    workspace_root: Path,
    template_overrides: dict[str, str] | None = None,
    external_policy: dict[str, object] | None = None,
) -> str:
    """Build a shell command from trusted template and escaped placeholders."""
    agent = (external_agent or "").strip()
    if not agent:
        raise ValueError("external_agent is required for template command build")
    templates = dict(DEFAULT_EXTERNAL_TEMPLATES)
    if template_overrides:
        for key, value in template_overrides.items():
            k = str(key).strip()
            v = str(value).strip()
            if k and v:
                templates[k] = v
    template = templates.get(agent)
    if not template:
        raise ValueError(f"unsupported external_agent: {agent}")

    template = _inject_resolved_executable(template, agent, external_policy)
    template = _ensure_codex_workspace_write_flag(template, agent)
    template = _ensure_cursor_trust_flag(template, agent)

    tokens = _PLACEHOLDER_RE.findall(template)
    unknown = sorted(set(token for token in tokens if token not in _ALLOWED_PLACEHOLDERS))
    if unknown:
        raise ValueError(f"template contains unsupported placeholders: {', '.join(unknown)}")

    replacements = {
        "prompt": shlex.quote(prompt.strip() or "请完成当前编码步骤并返回改动摘要。"),
        "workdir": shlex.quote(str(workspace_root)),
    }
    command = template
    for token in tokens:
        command = command.replace(f"{{{token}}}", replacements[token])
    return command
