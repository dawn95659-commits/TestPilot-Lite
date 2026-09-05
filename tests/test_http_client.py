from __future__ import annotations

import httpx
import pytest

from testpilot.http_client import LocalHttpClient
from testpilot.models import TestCase as APITestCase
from testpilot.validators import validate_execution


PORTS = frozenset({8001})


def test_fetch_openapi_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "simulated timeout",
            request=request,
        )

    client = LocalHttpClient(
        allowed_ports=PORTS,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.ReadTimeout, match="simulated timeout"):
        client.fetch_openapi(
            "http://127.0.0.1:8001/openapi.json"
        )


def test_execute_records_non_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html>not json</html>",
            headers={"Content-Type": "text/html"},
        )

    client = LocalHttpClient(
        allowed_ports=PORTS,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    case = APITestCase(
        case_id="non-json-case",
        operation_id="get_item",
        title="Non JSON response",
        category="happy",
        method="GET",
        path="/items/1",
        expected_status=200,
        expected_schema={
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
            },
            "required": ["id"],
        },
    )

    record = client.execute(
        case,
        base_url="http://127.0.0.1:8001",
        approved=False,
    )

    assert record.actual_status == 200
    assert record.response_json is None
    assert "<html>not json</html>" in record.response_text

    result = validate_execution(case, record)

    assert result.passed is False
    assert result.schema_valid is False
    assert any(
        "无法解析为 JSON" in error
        for error in result.errors
    )


def test_fetch_openapi_rejects_oversized_document() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 101,
        )

    client = LocalHttpClient(
        allowed_ports=PORTS,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
        max_openapi_bytes=100,
    )

    with pytest.raises(ValueError, match="超过"):
        client.fetch_openapi(
            "http://127.0.0.1:8001/openapi.json"
        )
import httpx

from testpilot.http_client import LocalHttpClient
from testpilot.models import TestCase


def _retry_case(
    method: str = "GET",
) -> TestCase:
    return TestCase(
        case_id=f"retry-{method.lower()}",
        operation_id="retry_test",
        title="Retry Test",
        category="happy",
        method=method,
        path="/retry-test",
        expected_status=200,
        needs_approval=(
            method.upper()
            not in {"GET", "HEAD", "OPTIONS"}
        ),
    )


def test_get_retries_transport_error_and_succeeds():
    calls = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        # 前两次模拟网络断开
        if calls < 3:
            raise httpx.ConnectError(
                "temporary connection failure",
                request=request,
            )

        # 第三次恢复
        return httpx.Response(
            200,
            json={"ok": True},
        )

    client = LocalHttpClient(
        allowed_ports=frozenset({8001}),
        transport=httpx.MockTransport(
            handler
        ),
        max_retries=2,
        retry_backoff_seconds=0,
    )

    record = client.execute(
        _retry_case("GET"),
        "http://127.0.0.1:8001",
        approved=False,
    )

    assert calls == 3
    assert record.actual_status == 200
    assert record.transport_error is None


def test_get_retries_503_and_succeeds():
    calls = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            return httpx.Response(
                503,
                json={
                    "detail":
                    "temporarily unavailable"
                },
            )

        return httpx.Response(
            200,
            json={"ok": True},
        )

    client = LocalHttpClient(
        allowed_ports=frozenset({8001}),
        transport=httpx.MockTransport(
            handler
        ),
        max_retries=2,
        retry_backoff_seconds=0,
    )

    record = client.execute(
        _retry_case("GET"),
        "http://127.0.0.1:8001",
        approved=False,
    )

    assert calls == 2
    assert record.actual_status == 200


def test_get_does_not_retry_404():
    calls = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(
            404,
            json={
                "detail": "not found"
            },
        )

    client = LocalHttpClient(
        allowed_ports=frozenset({8001}),
        transport=httpx.MockTransport(
            handler
        ),
        max_retries=2,
        retry_backoff_seconds=0,
    )

    record = client.execute(
        _retry_case("GET"),
        "http://127.0.0.1:8001",
        approved=False,
    )

    # 404 不是“临时网络故障”
    # 所以不能重试
    assert calls == 1
    assert record.actual_status == 404


def test_post_transport_error_is_not_retried():
    calls = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        raise httpx.ConnectError(
            "connection lost",
            request=request,
        )

    client = LocalHttpClient(
        allowed_ports=frozenset({8001}),
        transport=httpx.MockTransport(
            handler
        ),
        max_retries=5,
        retry_backoff_seconds=0,
    )

    case = _retry_case("POST")

    record = client.execute(
        case,
        "http://127.0.0.1:8001",
        approved=True,
    )

    # 即使 max_retries=5，
    # POST 也只允许请求一次
    assert calls == 1
    assert record.actual_status is None
    assert record.transport_error is not None
