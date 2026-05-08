"""Project introspection helpers for V3 built-in skills."""

from __future__ import annotations

from pathlib import Path


def inspect_workspace(workspace_root: str | Path | None) -> dict[str, object]:
    """Inspect the workspace and return a lightweight repo profile."""
    root = Path(workspace_root or ".").expanduser().resolve()
    entries = []
    if root.exists() and root.is_dir():
        entries = sorted(item.name for item in root.iterdir())

    tests_dir = root / "tests"
    has_python_tests = tests_dir.exists() and tests_dir.is_dir()
    has_pyproject = (root / "pyproject.toml").exists()
    has_requirements = (root / "requirements.txt").exists()
    has_gradle_kts = (root / "build.gradle.kts").exists() or (root / "settings.gradle.kts").exists()
    has_gradlew = (root / "gradlew").exists()
    candidate_test_targets = _discover_test_targets(root)

    repo_profile = "generic"
    candidate_test_commands: list[str] = []

    if has_gradle_kts:
        repo_profile = "gradle_kotlin"
        candidate_test_commands.append("./gradlew test" if has_gradlew else "gradle test")
    elif has_python_tests or has_pyproject or has_requirements:
        repo_profile = "python_pytest"
        for target in candidate_test_targets:
            candidate_test_commands.append(f"pytest -q {target}")
        candidate_test_commands.append("pytest -q")

    return {
        "workspace_root": str(root),
        "repo_profile": repo_profile,
        "root_entries": entries[:50],
        "has_python_tests": has_python_tests,
        "candidate_test_targets": candidate_test_targets,
        "candidate_test_commands": candidate_test_commands,
    }


def infer_goal_kind(goal: str) -> str:
    """Infer the high-level task kind from the user goal."""
    text = goal.lower()
    if any(keyword in text for keyword in ("修复", "fix", "bug", "实现", "add", "modify", "change", "update")):
        return "coding"
    if any(keyword in text for keyword in ("测试", "pytest", "test only", "run tests", "run all tests", "执行测试")):
        return "testing"
    if any(keyword in text for keyword in ("分析", "explain", "summarize", "review", "阅读代码")):
        return "analysis"
    return "general"


def _discover_test_targets(root: Path, *, limit: int = 3) -> list[str]:
    tests_dir = root / "tests"
    if not tests_dir.exists() or not tests_dir.is_dir():
        return []

    targets: list[str] = []
    for path in sorted(tests_dir.rglob("test_*.py")):
        try:
            targets.append(path.relative_to(root).as_posix())
        except ValueError:
            continue
        if len(targets) >= limit:
            break
    return targets
