from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Phase(str, Enum):
    INSPECTING = "inspecting"
    GENERATING = "generating"
    WAITING_APPROVAL = "waiting_approval"
    EXECUTING = "executing"
    SEARCHING_BUGS = "searching_bugs"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"


class ParameterSpec(BaseModel):
    name: str
    location: Literal["path", "query", "header", "cookie"]
    required: bool = False
    schema_data: dict[str, Any] = Field(default_factory=dict)


class OperationSpec(BaseModel):
    operation_id: str
    method: str
    path: str
    summary: str = ""
    parameters: list[ParameterSpec] = Field(default_factory=list)
    request_body_schema: dict[str, Any] | None = None
    request_body_required: bool = False
    responses: dict[str, dict[str, Any] | None] = Field(default_factory=dict)


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    operation_id: str
    title: str
    category: Literal["happy", "boundary", "negative"]
    method: str
    path: str
    path_params: dict[str, Any] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    json_body: Any | None = None
    expected_status: int
    expected_schema: dict[str, Any] | None = None
    needs_approval: bool = False

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()


class ExecutionRecord(BaseModel):
    case_id: str
    actual_status: int | None = None
    latency_ms: float = 0.0
    response_json: Any | None = None
    response_text: str = ""
    blocked: bool = False
    transport_error: str | None = None


class TestResult(BaseModel):
    case_id: str
    passed: bool
    actual_status: int | None = None
    latency_ms: float = 0.0
    schema_valid: bool | None = None
    blocked: bool = False
    errors: list[str] = Field(default_factory=list)


class BugAdvice(BaseModel):
    bug_id: str
    title: str
    score: float
    likely_cause: str
    checks: list[str]


class TraceEvent(BaseModel):
    step: int
    phase: Phase
    tool_name: str
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


class ToolDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: Literal[
        "inspect_openapi",
        "generate_test_cases",
        "execute_tests",
        "search_bug_knowledge",
        "save_report",
        "finish",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str


class AgentState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    openapi_url: str
    base_url: str | None = None
    phase: Phase = Phase.INSPECTING
    operations: list[OperationSpec] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    results: list[TestResult] = Field(default_factory=list)
    bug_advice: list[BugAdvice] = Field(default_factory=list)
    approval_granted: bool | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    step_count: int = 0
    max_cases: int = 12
    report_json_path: str | None = None
    report_markdown_path: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def requires_approval(self) -> bool:
        return any(case.needs_approval for case in self.test_cases)


class CreateSessionRequest(BaseModel):
    openapi_url: HttpUrl
    goal: str = Field(min_length=3, max_length=500)
    max_cases: int = Field(default=12, ge=1, le=20)


class ApprovalRequest(BaseModel):
    approved: bool

