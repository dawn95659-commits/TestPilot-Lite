from __future__ import annotations

import json
from typing import Protocol

import httpx
from pydantic import ValidationError

from .config import Settings
from .models import AgentState, Phase, ToolDecision


class Planner(Protocol):
    def decide(self, state: AgentState) -> ToolDecision: ...


class PlannerRecoverableError(RuntimeError):
    """LLM Planner 出现可恢复错误时使用。

    这类错误允许 FallbackPlanner 回退到 HeuristicPlanner。

    例如：
    - LLM 返回非法 JSON
    - LLM 返回错误 Tool
    - LLM 响应结构异常

    注意：
    WAITING_APPROVAL 等安全状态不属于可恢复错误。
    """


class HeuristicPlanner:
    """默认的确定性 Planner。

    优点：
    - 可重复
    - 不依赖 LLM
    - 适合 pytest
    - 适合 evaluation
    - 作为 LLM Planner 的 fallback
    """

    TOOL_BY_PHASE = {
        Phase.INSPECTING: "inspect_openapi",
        Phase.GENERATING: "generate_test_cases",
        Phase.EXECUTING: "execute_tests",
        Phase.SEARCHING_BUGS: "search_bug_knowledge",
        Phase.REPORTING: "save_report",
        Phase.COMPLETED: "finish",
    }

    def decide(self, state: AgentState) -> ToolDecision:
        # Human-in-the-loop 安全边界。
        # WAITING_APPROVAL 状态绝对不能继续自动规划。
        if state.phase == Phase.WAITING_APPROVAL:
            raise RuntimeError(
                "Agent 正在等待人工审批，不能继续自动规划"
            )

        if state.phase == Phase.FAILED:
            return ToolDecision(
                tool_name="finish",
                reason="任务已经失败，结束循环",
            )

        tool = self.TOOL_BY_PHASE.get(state.phase)

        if tool is None:
            raise RuntimeError(
                f"当前 Phase 没有对应工具: {state.phase}"
            )

        reasons = {
            "inspect_openapi": (
                "先读取接口契约，才能知道有哪些可测试操作"
            ),
            "generate_test_cases": (
                "已获得接口结构，生成正常、边界和异常用例"
            ),
            "execute_tests": (
                "用例已准备且审批状态明确，执行确定性测试工具"
            ),
            "search_bug_knowledge": (
                "存在失败用例，检索历史 Bug 知识提供排查方向"
            ),
            "save_report": (
                "执行和诊断完成，输出结构化报告"
            ),
            "finish": (
                "报告已经保存，结束 Agent 循环"
            ),
        }

        return ToolDecision(
            tool_name=tool,
            reason=reasons[tool],
        )


class CompatibleLLMPlanner:
    """OpenAI-compatible Chat Completions Planner。

    LLM 只能选择下一 Tool。

    它不能：
    - 自己发送业务 HTTP 请求
    - 绕过 Human Approval
    - 随意跳过 Agent Phase

    最终 ToolDecision 还会经过 Python Guardrail。
    """

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not (
            settings.llm_base_url
            and settings.llm_api_key
            and settings.llm_model
        ):
            raise ValueError(
                "LLM 规划器需要 "
                "LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL"
            )

        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

        # 正常运行时为 None。
        # pytest 时可以注入 httpx.MockTransport。
        self.transport = transport

    def decide(self, state: AgentState) -> ToolDecision:
        # -------------------------------------------------
        # 1. Human-in-the-loop Guardrail
        # -------------------------------------------------
        if state.phase == Phase.WAITING_APPROVAL:
            raise RuntimeError(
                "Agent 正在等待人工审批，不能继续自动规划"
            )

        if state.phase == Phase.FAILED:
            return ToolDecision(
                tool_name="finish",
                reason="任务已经失败，结束循环",
            )

        # 当前 Phase 实际允许的 Tool。
        expected_tool = HeuristicPlanner.TOOL_BY_PHASE.get(
            state.phase
        )

        if expected_tool is None:
            raise RuntimeError(
                f"当前 Phase 没有对应工具: {state.phase}"
            )

        # 给模型看的工具列表。
        # dict.fromkeys 用于去重。
        allowed = list(
            dict.fromkeys(
                HeuristicPlanner.TOOL_BY_PHASE.values()
            )
        )

        prompt = {
            "goal": state.goal,
            "phase": state.phase.value,
            "operation_count": len(state.operations),
            "case_count": len(state.test_cases),
            "result_count": len(state.results),
            "failed_count": sum(
                not item.passed and not item.blocked
                for item in state.results
            ),
            "approval_granted": state.approval_granted,
            "allowed_tools": allowed,
        }

        # -------------------------------------------------
        # 2. 请求 LLM
        # -------------------------------------------------
        try:
            with httpx.Client(
                timeout=15,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": (
                            f"Bearer {self.api_key}"
                        )
                    },
                    json={
                        "model": self.model,
                        "temperature": 0,
                        "response_format": {
                            "type": "json_object"
                        },
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "你是测试 Agent 规划器。"
                                    "只决定下一工具，不执行请求。"
                                    "严格输出 JSON："
                                    "tool_name, arguments, reason。"
                                ),
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    prompt,
                                    ensure_ascii=False,
                                ),
                            },
                        ],
                    },
                )

            # 400 / 401 / 500 等会在这里转成
            # httpx.HTTPStatusError。
            response.raise_for_status()

        except httpx.HTTPError:
            # 网络类异常交给 FallbackPlanner 处理。
            raise

        # -------------------------------------------------
        # 3. 解析 OpenAI-compatible Response
        # -------------------------------------------------
        try:
            payload = response.json()

            content = (
                payload["choices"][0]
                ["message"]["content"]
            )

            if not isinstance(content, str):
                raise TypeError(
                    "LLM message.content 必须是字符串"
                )

        except (
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise PlannerRecoverableError(
                "LLM 响应结构不合法"
            ) from exc

        # -------------------------------------------------
        # 4. Pydantic 校验 ToolDecision
        # -------------------------------------------------
        try:
            decision = ToolDecision.model_validate_json(
                content
            )

        except (ValidationError, TypeError) as exc:
            raise PlannerRecoverableError(
                "LLM 没有返回合法的 ToolDecision"
            ) from exc

        # -------------------------------------------------
        # 5. Phase → Tool Guardrail
        # -------------------------------------------------
        # 例如：
        #
        # Phase = GENERATING
        #
        # 正确：
        # generate_test_cases
        #
        # 错误：
        # execute_tests
        #
        # 模型即使返回一个存在的工具，
        # 只要与当前 Phase 不匹配，也拒绝。
        if decision.tool_name != expected_tool:
            raise PlannerRecoverableError(
                "LLM 工具选择违反 Phase Guardrail: "
                f"phase={state.phase.value}, "
                f"expected={expected_tool}, "
                f"actual={decision.tool_name}"
            )

        return decision


class FallbackPlanner:
    """优先使用 primary Planner，失败后回退到 fallback Planner。

    默认设计：
        primary  = CompatibleLLMPlanner
        fallback = HeuristicPlanner

    只处理“可恢复”的 LLM 故障。

    不捕获 RuntimeError，
    所以 WAITING_APPROVAL 等安全限制不会被绕过。
    """

    def __init__(
        self,
        primary: Planner,
        fallback: Planner,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

        # 方便调试和测试。
        self.last_fallback_reason: str | None = None

    def decide(self, state: AgentState) -> ToolDecision:
        self.last_fallback_reason = None

        try:
            return self.primary.decide(state)

        except (
            httpx.HTTPError,
            PlannerRecoverableError,
        ) as exc:
            self.last_fallback_reason = (
                f"{type(exc).__name__}: {exc}"
            )

            fallback_decision = self.fallback.decide(
                state
            )

            # Trace 中能看出来这一轮实际上发生了 fallback。
            return ToolDecision(
                tool_name=fallback_decision.tool_name,
                arguments=fallback_decision.arguments,
                reason=(
                    "LLM 规划失败，已回退到 "
                    "HeuristicPlanner"
                    f"（{type(exc).__name__}）；"
                    f"{fallback_decision.reason}"
                ),
            )


def build_planner(settings: Settings) -> Planner:
    if settings.planner == "llm":
        return FallbackPlanner(
            primary=CompatibleLLMPlanner(settings),
            fallback=HeuristicPlanner(),
        )

    return HeuristicPlanner()
