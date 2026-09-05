from __future__ import annotations

from pathlib import Path

from testpilot.bug_search import BugKnowledgeBase
from testpilot.models import ExecutionRecord, TestCase as APITestCase
from testpilot.validators import validate_execution


def make_case() -> APITestCase:
    return APITestCase(
        case_id="case-1",
        operation_id="get_item",
        title="Get item",
        category="happy",
        method="GET",
        path="/items/1",
        expected_status=200,
        expected_schema={
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    )


def test_validation_passes() -> None:
    result = validate_execution(
        make_case(),
        ExecutionRecord(case_id="case-1", actual_status=200, response_json={"id": 1}),
    )
    assert result.passed is True
    assert result.schema_valid is True


def test_validation_reports_status_mismatch() -> None:
    result = validate_execution(
        make_case(),
        ExecutionRecord(case_id="case-1", actual_status=500, response_json={"id": 1}),
    )
    assert result.passed is False
    assert "状态码" in result.errors[0]


def test_validation_reports_schema_mismatch() -> None:
    result = validate_execution(
        make_case(),
        ExecutionRecord(case_id="case-1", actual_status=200, response_json={"id": "wrong"}),
    )
    assert result.schema_valid is False
    assert result.passed is False


def test_blocked_write_is_recorded() -> None:
    result = validate_execution(make_case(), ExecutionRecord(case_id="case-1", blocked=True))
    assert result.blocked is True
    assert result.passed is False


def test_bug_search_finds_404_entry() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "bug_knowledge.json"
    results = BugKnowledgeBase(path).search("404 资源不存在 not found")
    assert results[0].bug_id == "fixture-404"


def test_bug_search_returns_empty_for_unrelated_query() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "bug_knowledge.json"
    results = BugKnowledgeBase(path).search("zzzzzzqqqqq")
    assert results == []
