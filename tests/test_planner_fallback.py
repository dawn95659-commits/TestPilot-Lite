from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from testpilot.models import AgentState, Phase
from testpilot.planner import (
    CompatibleLLMPlanner,
    FallbackPlanner,
    HeuristicPlanner,
)


def make_state(
    phase: Phase = Phase.GENERATING,
) -> AgentState:
    """只构造 Planner 测试需要的 AgentState 字段。

    model_construct() 不走完整 Pydantic 校验，
    所以不用知道 AgentState 其他必填字段。
    """

    return AgentState.model_construct(
        goal="测试 Planner",
        phase=phase,
        operations=[],
        test_cases=[],
        results=[],
        approval_granted=False,
    )


def fake_settings():
    """CompatibleLLMPlanner 测试用配置。

    不需要真正 API Key。
    因为测试使用 MockTransport。
    """

    return SimpleNamespace(
        llm_base_url="http://fake-llm.local",
        llm_api_key="test-key",
        llm_model="fake-model",
    )


def llm_response(
    request: httpx.Request,
    tool_name: str,
) -> httpx.Response:
    """构造一个 OpenAI-compatible 假响应。"""

    content = json.dumps(
        {
            "tool_name": tool_name,
            "arguments": {},
            "reason": "fake llm decision",
        },
        ensure_ascii=False,
    )

    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": content
                    }
                }
            ]
        },
        request=request,
    )


# ---------------------------------------------------------
# 1. HeuristicPlanner 基础映射
# ---------------------------------------------------------

@pytest.mark.parametrize(
    ("phase", "expected_tool"),
    [
        (
            Phase.INSPECTING,
            "inspect_openapi",
        ),
        (
            Phase.GENERATING,
            "generate_test_cases",
        ),
        (
            Phase.EXECUTING,
            "execute_tests",
        ),
        (
            Phase.SEARCHING_BUGS,
            "search_bug_knowledge",
        ),
        (
            Phase.REPORTING,
            "save_report",
        ),
    ],
)
def test_heuristic_selects_correct_tool(
    phase: Phase,
    expected_tool: str,
) -> None:
    planner = HeuristicPlanner()

    decision = planner.decide(
        make_state(phase)
    )

    assert decision.tool_name == expected_tool


# ---------------------------------------------------------
# 2. WAITING_APPROVAL 必须拒绝
# ---------------------------------------------------------

def test_heuristic_blocks_waiting_approval() -> None:
    planner = HeuristicPlanner()

    with pytest.raises(
        RuntimeError,
        match="等待人工审批",
    ):
        planner.decide(
            make_state(
                Phase.WAITING_APPROVAL
            )
        )


# ---------------------------------------------------------
# 3. LLM 返回正确 Tool
# ---------------------------------------------------------

def test_llm_valid_decision_is_used() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return llm_response(
            request,
            "generate_test_cases",
        )

    transport = httpx.MockTransport(
        handler
    )

    planner = CompatibleLLMPlanner(
        fake_settings(),
        transport=transport,
    )

    decision = planner.decide(
        make_state(Phase.GENERATING)
    )

    assert (
        decision.tool_name
        == "generate_test_cases"
    )


# ---------------------------------------------------------
# 4. LLM 选择错误 Tool → fallback
# ---------------------------------------------------------

def test_wrong_llm_tool_falls_back() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        # 当前 phase 是 GENERATING，
        # 正确应该 generate_test_cases。
        #
        # 我们故意让模型返回 execute_tests。
        return llm_response(
            request,
            "execute_tests",
        )

    transport = httpx.MockTransport(
        handler
    )

    llm = CompatibleLLMPlanner(
        fake_settings(),
        transport=transport,
    )

    planner = FallbackPlanner(
        primary=llm,
        fallback=HeuristicPlanner(),
    )

    decision = planner.decide(
        make_state(Phase.GENERATING)
    )

    assert (
        decision.tool_name
        == "generate_test_cases"
    )

    assert "回退" in decision.reason

    assert (
        planner.last_fallback_reason
        is not None
    )


# ---------------------------------------------------------
# 5. LLM 返回非法 JSON → fallback
# ---------------------------------------------------------

def test_invalid_llm_json_falls_back() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "this is not json"
                            )
                        }
                    }
                ]
            },
            request=request,
        )

    transport = httpx.MockTransport(
        handler
    )

    llm = CompatibleLLMPlanner(
        fake_settings(),
        transport=transport,
    )

    planner = FallbackPlanner(
        primary=llm,
        fallback=HeuristicPlanner(),
    )

    decision = planner.decide(
        make_state(Phase.GENERATING)
    )

    assert (
        decision.tool_name
        == "generate_test_cases"
    )

    assert "回退" in decision.reason


# ---------------------------------------------------------
# 6. LLM 网络连接失败 → fallback
# ---------------------------------------------------------

def test_llm_connect_error_falls_back() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ConnectError(
            "fake llm is down",
            request=request,
        )

    transport = httpx.MockTransport(
        handler
    )

    llm = CompatibleLLMPlanner(
        fake_settings(),
        transport=transport,
    )

    planner = FallbackPlanner(
        primary=llm,
        fallback=HeuristicPlanner(),
    )

    decision = planner.decide(
        make_state(Phase.GENERATING)
    )

    assert (
        decision.tool_name
        == "generate_test_cases"
    )

    assert "回退" in decision.reason


# ---------------------------------------------------------
# 7. LLM 返回 HTTP 500 → fallback
# ---------------------------------------------------------

def test_llm_http_500_falls_back() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "detail": "fake server error"
            },
            request=request,
        )

    transport = httpx.MockTransport(
        handler
    )

    llm = CompatibleLLMPlanner(
        fake_settings(),
        transport=transport,
    )

    planner = FallbackPlanner(
        primary=llm,
        fallback=HeuristicPlanner(),
    )

    decision = planner.decide(
        make_state(Phase.GENERATING)
    )

    assert (
        decision.tool_name
        == "generate_test_cases"
    )

    assert "回退" in decision.reason


# ---------------------------------------------------------
# 8. Fallback 绝不能绕过人工审批
# ---------------------------------------------------------

def test_fallback_does_not_bypass_approval() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        # 正常情况下这里甚至不应该执行到。
        return llm_response(
            request,
            "execute_tests",
        )

    transport = httpx.MockTransport(
        handler
    )

    llm = CompatibleLLMPlanner(
        fake_settings(),
        transport=transport,
    )

    planner = FallbackPlanner(
        primary=llm,
        fallback=HeuristicPlanner(),
    )

    with pytest.raises(
        RuntimeError,
        match="等待人工审批",
    ):
        planner.decide(
            make_state(
                Phase.WAITING_APPROVAL
            )
        )
