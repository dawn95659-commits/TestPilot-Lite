from __future__ import annotations

from collections.abc import Callable

from .bug_search import BugKnowledgeBase
from .case_generator import generate_test_cases
from .config import Settings
from .http_client import LocalHttpClient
from .models import AgentState, Phase, TraceEvent
from .openapi_parser import parse_openapi
from .planner import Planner
from .reporting import save_report
from .security import base_url_from_openapi_url
from .store import SessionStore
from .validators import validate_execution


class AgentController:
    def __init__(
        self,
        settings: Settings,
        store: SessionStore,
        planner: Planner,
        http_client: LocalHttpClient,
        bug_knowledge: BugKnowledgeBase,
    ) -> None:
        self.settings = settings
        self.store = store
        self.planner = planner
        self.http_client = http_client
        self.bug_knowledge = bug_knowledge
        self.tools: dict[str, Callable[[AgentState, dict], None]] = {
            "inspect_openapi": self._inspect_openapi,
            "generate_test_cases": self._generate_test_cases,
            "execute_tests": self._execute_tests,
            "search_bug_knowledge": self._search_bug_knowledge,
            "save_report": self._save_report,
            "finish": self._finish,
        }

    def create(self, goal: str, openapi_url: str, max_cases: int) -> AgentState:
        state = AgentState(goal=goal, openapi_url=openapi_url, max_cases=max_cases)
        self.store.save(state)
        return self.run(state)

    def approve(self, state: AgentState, approved: bool) -> AgentState:
        if state.phase != Phase.WAITING_APPROVAL:
            raise ValueError("当前会话不处于等待审批状态")
        state.approval_granted = approved
        state.phase = Phase.EXECUTING
        self.store.save(state)
        return self.run(state)

    def run(self, state: AgentState) -> AgentState:
        try:
            while state.phase not in {Phase.WAITING_APPROVAL, Phase.COMPLETED, Phase.FAILED}:
                if state.step_count >= self.settings.max_steps:
                    raise RuntimeError("超过 Agent 最大步数，已停止")
                decision = self.planner.decide(state)
                tool = self.tools.get(decision.tool_name)
                if tool is None:
                    raise RuntimeError(f"规划器选择了未知工具：{decision.tool_name}")
                state.step_count += 1
                state.trace.append(
                    TraceEvent(
                        step=state.step_count,
                        phase=state.phase,
                        tool_name=decision.tool_name,
                        reason=decision.reason,
                    )
                )
                tool(state, decision.arguments)
                self.store.save(state)
        except Exception as exc:  # API boundary records the failure for inspection.
            state.phase = Phase.FAILED
            state.error = f"{type(exc).__name__}: {exc}"
            self.store.save(state)
        return state

    def _inspect_openapi(self, state: AgentState, _: dict) -> None:
        document = self.http_client.fetch_openapi(state.openapi_url)
        state.operations = parse_openapi(document)
        state.base_url = base_url_from_openapi_url(state.openapi_url)
        state.phase = Phase.GENERATING

    def _generate_test_cases(self, state: AgentState, arguments: dict) -> None:
        requested = int(arguments.get("max_cases", state.max_cases))
        count = min(requested, state.max_cases, self.settings.max_cases, 20)
        state.test_cases = generate_test_cases(state.operations, max_cases=count)
        state.phase = Phase.WAITING_APPROVAL if state.requires_approval else Phase.EXECUTING

    def _execute_tests(self, state: AgentState, _: dict) -> None:
        if state.base_url is None:
            raise RuntimeError("尚未解析目标 base URL")
        approved = state.approval_granted is True
        state.results = []
        for case in state.test_cases:
            record = self.http_client.execute(case, state.base_url, approved=approved)
            state.results.append(validate_execution(case, record))
        has_failures = any(not item.passed and not item.blocked for item in state.results)
        state.phase = Phase.SEARCHING_BUGS if has_failures else Phase.REPORTING

    def _search_bug_knowledge(self, state: AgentState, _: dict) -> None:
        seen: set[str] = set()
        state.bug_advice = []
        case_by_id = {case.case_id: case for case in state.test_cases}
        for result in state.results:
            if result.passed or result.blocked:
                continue
            case = case_by_id[result.case_id]
            query = " ".join([case.title, str(result.actual_status), *result.errors])
            for advice in self.bug_knowledge.search(query, top_k=2):
                if advice.bug_id not in seen:
                    state.bug_advice.append(advice)
                    seen.add(advice.bug_id)
        state.phase = Phase.REPORTING

    def _save_report(self, state: AgentState, _: dict) -> None:
        json_path, markdown_path = save_report(state, self.settings.reports_dir)
        state.report_json_path = str(json_path)
        state.report_markdown_path = str(markdown_path)
        state.phase = Phase.COMPLETED

    def _finish(self, state: AgentState, _: dict) -> None:
        state.phase = Phase.COMPLETED

