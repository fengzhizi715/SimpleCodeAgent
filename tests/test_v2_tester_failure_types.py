"""Tester 失败类型判定。"""

from __future__ import annotations

from app.v2.agent_impls.tester import TesterAgent


def test_infer_no_tests_collected() -> None:
    agent = TesterAgent()
    assert (
        agent._infer_failure_type(stdout="no tests ran in 0.00s\n", stderr="") == "no_tests_collected"
    )
    assert agent._infer_failure_type(stdout="", stderr="collected 0 items") == "no_tests_collected"
