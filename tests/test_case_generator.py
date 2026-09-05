from __future__ import annotations

from testpilot.case_generator import generate_test_cases
from testpilot.openapi_parser import parse_openapi


def test_generates_happy_cases(openapi_document: dict) -> None:
    cases = generate_test_cases(parse_openapi(openapi_document), max_cases=20)
    happy_ids = {case.case_id for case in cases if case.category == "happy"}
    assert happy_ids == {"list_items-happy", "get_item-happy", "create_order-happy"}


def test_generates_not_found_case(openapi_document: dict) -> None:
    cases = generate_test_cases(parse_openapi(openapi_document), max_cases=20)
    missing = next(case for case in cases if case.case_id == "get_item-not-found")
    assert missing.path_params == {"item_id": 999999}
    assert missing.expected_status == 404


def test_generates_missing_body_case(openapi_document: dict) -> None:
    cases = generate_test_cases(parse_openapi(openapi_document), max_cases=20)
    missing = next(case for case in cases if case.case_id == "create_order-missing-body")
    assert missing.json_body is None
    assert missing.expected_status == 422


def test_write_cases_require_approval(openapi_document: dict) -> None:
    cases = generate_test_cases(parse_openapi(openapi_document), max_cases=20)
    assert all(case.needs_approval for case in cases if case.method == "POST")
    assert all(not case.needs_approval for case in cases if case.method == "GET")


def test_respects_max_cases(openapi_document: dict) -> None:
    cases = generate_test_cases(parse_openapi(openapi_document), max_cases=2)
    assert len(cases) == 2


def test_builds_required_request_body(openapi_document: dict) -> None:
    cases = generate_test_cases(parse_openapi(openapi_document), max_cases=20)
    case = next(item for item in cases if item.case_id == "create_order-happy")
    assert case.json_body == {"product_id": 1, "quantity": 1}

