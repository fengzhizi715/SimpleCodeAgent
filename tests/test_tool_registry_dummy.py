"""ToolRegistry 注册 DummyTool、列举定义，以及 ToolRouter.route 调用的简单测试。"""

from __future__ import annotations

from app.v1.tools.base import DummyTool
from app.v1.tools.registry import ToolRegistry
from app.v1.tools.router import ToolRouter


def test_register_dummy_tool_list_definitions_and_route() -> None:
    registry = ToolRegistry()
    registry.register(DummyTool(workspace_root=registry.workspace_root))

    definitions = registry.get_tool_definitions()
    assert len(definitions) == 1
    assert definitions[0].name == "dummy_tool"

    router = ToolRouter(registry)
    result = router.route(
        "dummy_tool",
        {"input": "hello"},
        tool_call_id="test-call-1",
    )
    print(result.content)

    assert result.name == "dummy_tool"
    assert result.tool_call_id == "test-call-1"
    assert result.is_error is False
    assert "hello" in result.content