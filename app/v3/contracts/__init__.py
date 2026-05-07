"""V3 protocol definitions."""

from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.execution_contracts import ExecutionReport, ExecutionStatus
from app.v3.contracts.graph_contracts import TaskGraph, TaskNode, TaskNodeStatus
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec, SkillType
from app.v3.contracts.trigger_contracts import TriggerRule

__all__ = [
    "EventType",
    "ExecutionReport",
    "ExecutionStatus",
    "SkillInput",
    "SkillOutput",
    "SkillSpec",
    "SkillType",
    "TaskGraph",
    "TaskNode",
    "TaskNodeStatus",
    "TriggerRule",
    "V3Event",
]
