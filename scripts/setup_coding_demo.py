#!/usr/bin/env python
"""生成小范围编程任务演示工作区。"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = PROJECT_ROOT / "demo_workspace"


FILES: dict[str, str] = {
    "README.md": """# Coding Demo Workspace

这个目录用于验证 Agent 的小范围编程能力。

建议任务：

1. 新建 `utils/string_utils.py`
   目标：让 `tests/test_string_utils.py` 通过

2. 为 `services/todo_service.py` 新增 CRUD 方法
   目标：让 `tests/test_todo_service.py` 通过

3. 参考 `services/order_service.py` 仿写 `services/product_service.py`
   目标：让 `tests/test_product_service.py` 通过

4. 修复 `utils/math_utils.py`
   目标：让 `tests/test_math_utils.py` 通过

推荐验证命令：

```bash
.venv/bin/pytest demo_workspace/tests/test_string_utils.py
.venv/bin/pytest demo_workspace/tests/test_todo_service.py
.venv/bin/pytest demo_workspace/tests/test_product_service.py
.venv/bin/pytest demo_workspace/tests/test_math_utils.py
```
""",
    "__init__.py": "",
    "services/__init__.py": "",
    "utils/__init__.py": "",
    "services/order_service.py": """class OrderService:
    def __init__(self) -> None:
        self._orders: dict[str, dict[str, object]] = {}

    def create_order(self, order_id: str, amount: float) -> dict[str, object]:
        order = {"id": order_id, "amount": amount}
        self._orders[order_id] = order
        return order

    def get_order(self, order_id: str) -> dict[str, object] | None:
        return self._orders.get(order_id)

    def list_orders(self) -> list[dict[str, object]]:
        return list(self._orders.values())
""",
    "services/todo_service.py": """class TodoService:
    def __init__(self) -> None:
        self._todos: dict[str, dict[str, object]] = {}

    def create_todo(self, todo_id: str, title: str) -> dict[str, object]:
        todo = {"id": todo_id, "title": title, "done": False}
        self._todos[todo_id] = todo
        return todo

    def get_todo(self, todo_id: str) -> dict[str, object] | None:
        return self._todos.get(todo_id)

    def list_todos(self) -> list[dict[str, object]]:
        return list(self._todos.values())
""",
    "utils/math_utils.py": """def multiply(a: int, b: int) -> int:
    return a + b
""",
    "tests/test_string_utils.py": """from demo_workspace.utils.string_utils import StringUtils


def test_to_snake_case() -> None:
    assert StringUtils.to_snake_case("HelloWorld") == "hello_world"


def test_truncate() -> None:
    assert StringUtils.truncate("abcdef", 4) == "a..."
""",
    "tests/test_todo_service.py": """from demo_workspace.services.todo_service import TodoService


def test_todo_crud() -> None:
    service = TodoService()
    created = service.create_todo("t1", "write tests")
    assert created["done"] is False

    updated = service.update_todo("t1", title="write more tests", done=True)
    assert updated["title"] == "write more tests"
    assert updated["done"] is True

    deleted = service.delete_todo("t1")
    assert deleted["id"] == "t1"
    assert service.get_todo("t1") is None
""",
    "tests/test_product_service.py": """from demo_workspace.services.product_service import ProductService


def test_product_service_matches_order_style() -> None:
    service = ProductService()
    created = service.create_product("p1", "Keyboard", 199.0)
    assert created == {"id": "p1", "name": "Keyboard", "price": 199.0}
    assert service.get_product("p1") == created
    assert service.list_products() == [created]
""",
    "tests/test_math_utils.py": """from demo_workspace.utils.math_utils import multiply


def test_multiply() -> None:
    assert multiply(3, 4) == 12
""",
    "tests/conftest.py": """from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
""",
}


def main() -> None:
    """生成演示工作区文件。"""
    if DEMO_ROOT.exists():
        for path in sorted(DEMO_ROOT.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    for relative_path, content in FILES.items():
        target = DEMO_ROOT / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    print(f"demo_workspace_ready={DEMO_ROOT}")


if __name__ == "__main__":
    main()
