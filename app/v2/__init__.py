"""V2 中心化多 Agent 实现。"""

from app.v2.factory import build_default_registry, build_orchestrator_runtime
from app.v2.runtime import OrchestratorRuntime

__all__ = [
    "OrchestratorRuntime",
    "build_default_registry",
    "build_orchestrator_runtime",
]
