from __future__ import annotations

from jsonschema import ValidationError, validate

from .models import ExecutionRecord, TestCase, TestResult


def validate_execution(case: TestCase, record: ExecutionRecord) -> TestResult:
    errors: list[str] = []
    schema_valid: bool | None = None

    if record.blocked:
        return TestResult(
            case_id=case.case_id,
            passed=False,
            blocked=True,
            errors=["安全策略拦截：写操作未获批准"],
        )
    if record.transport_error:
        errors.append(f"请求失败：{record.transport_error}")
    if record.actual_status != case.expected_status:
        errors.append(f"状态码应为 {case.expected_status}，实际为 {record.actual_status}")

    if case.expected_schema is not None and record.response_json is not None:
        try:
            validate(instance=record.response_json, schema=case.expected_schema)
            schema_valid = True
        except ValidationError as exc:
            schema_valid = False
            errors.append(f"响应结构不匹配：{exc.message}")
    elif case.expected_schema is not None:
        schema_valid = False
        errors.append("预期 JSON 响应，但实际无法解析为 JSON")

    return TestResult(
        case_id=case.case_id,
        passed=not errors,
        actual_status=record.actual_status,
        latency_ms=record.latency_ms,
        schema_valid=schema_valid,
        blocked=False,
        errors=errors,
    )

