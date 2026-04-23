"""Compatibility layer for shared V2 agent helpers.

Prefer importing from:
- app.v2.agent_impls.payloads
- app.v2.agent_impls.llm_utils
- app.v2.agent_impls.workspace_diff
"""

from app.v2.agent_impls.llm_utils import chat_json, extract_json_object, parse_tool_content
from app.v2.agent_impls.payloads import (
    AnalysisFilePayload,
    AnalystOutputPayload,
    PLANNER_TOOL_HINTS,
    PlannerOutputPayload,
    PlannerStepPayload,
    ReviewIssuePayload,
    ReviewOutputPayload,
)
from app.v2.agent_impls.workspace_diff import (
    IGNORED_DIR_NAMES,
    TEXT_FILE_SUFFIXES,
    build_workspace_diff,
    is_text_candidate,
    relative_path,
    snapshot_workspace,
)

__all__ = [
    "PLANNER_TOOL_HINTS",
    "PlannerStepPayload",
    "PlannerOutputPayload",
    "AnalysisFilePayload",
    "AnalystOutputPayload",
    "ReviewIssuePayload",
    "ReviewOutputPayload",
    "extract_json_object",
    "parse_tool_content",
    "chat_json",
    "IGNORED_DIR_NAMES",
    "TEXT_FILE_SUFFIXES",
    "relative_path",
    "is_text_candidate",
    "snapshot_workspace",
    "build_workspace_diff",
]
