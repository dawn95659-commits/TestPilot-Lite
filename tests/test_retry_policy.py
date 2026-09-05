from __future__ import annotations

import httpx

from testpilot.http_client import LocalHttpClient
from testpilot.models import TestCase
from unittest.mock import patch


BASE_URL = "http://127.0.0.1:8001"


def _make_case(
    method: str,
    *,
    expected_status: int = 200,
) -> TestCase:
    """
    创建一个专门用于 Retry 测试的 TestCase。
    """
    method = method.upper()

    return TestCase(
        case_id=f"retry-{method.lower()}",
        operation_id=f"retry_{method.lower()}",
        title=f"{method} retry policy test",
        category="happy",
        method=method,
        path="/resource",
        json_body=(
            {"name": "demo"}
            if method in {"POST", "PUT", "PATCH"}
            else None
        ),
        expected_status=expected_status,
        needs_approval=method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        },
    )


def _client(
    transport: httpx.MockTransport,
) -> LocalHttpClient:
    """
    创建使用 MockTransport 的 LocalHttpClient。

    如果你当前 LocalHttpClient 的 Retry 是默认开启的，
    这里不用再传额外参数。
    """
    return LocalHttpClient(
        allowed_ports=frozenset({8001}),
        timeout_seconds=0.1,
        transport=transport,
        max_retries=1,
        retry_backoff_seconds=0,
    )


# ---------------------------------------------------------
# 1. GET Timeout：应该 Retry
# ---------------------------------------------------------
def test_get_timeout_retries_then_succeeds() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        # 第一次模拟网络超时
        if attempts == 1:
            raise httpx.ReadTimeout(
                "temporary timeout",
                request=request,
            )

        # 第二次恢复正常
        return httpx.Response(
            200,
            json={"ok": True},
        )

    transport = httpx.MockTransport(handler)
    client = _client(transport)

    case = _make_case(
        "GET",
        expected_status=200,
    )

    record = client.execute(
        case,
        BASE_URL,
        approved=False,
    )

    # 第一次超时 + 第二次成功
    assert attempts == 2

    # 最终拿到成功响应
    assert record.actual_status == 200
    assert record.transport_error is None


# ---------------------------------------------------------
# 2. GET 503：应该 Retry
# ---------------------------------------------------------
def test_get_503_retries_then_succeeds() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        # 第一次模拟服务暂时不可用
        if attempts == 1:
            return httpx.Response(
                503,
                json={"detail": "temporarily unavailable"},
            )

        # 第二次恢复
        return httpx.Response(
            200,
            json={"ok": True},
        )

    transport = httpx.MockTransport(handler)
    client = _client(transport)

    case = _make_case(
        "GET",
        expected_status=200,
    )

    record = client.execute(
        case,
        BASE_URL,
        approved=False,
    )

    assert attempts == 2
    assert record.actual_status == 200
    assert record.transport_error is None


# ---------------------------------------------------------
# 3. GET 404：不应该 Retry
# ---------------------------------------------------------
def test_get_404_does_not_retry() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            404,
            json={"detail": "not found"},
        )

    transport = httpx.MockTransport(handler)
    client = _client(transport)

    case = _make_case(
        "GET",
        expected_status=404,
    )

    record = client.execute(
        case,
        BASE_URL,
        approved=False,
    )

    # 404 不是临时网络问题，
    # 请求一次就应该结束
    assert attempts == 1
    assert record.actual_status == 404


# ---------------------------------------------------------
# 4. POST Timeout：不应该 Retry
# ---------------------------------------------------------
def test_post_timeout_does_not_retry() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        raise httpx.ReadTimeout(
            "timeout after sending POST",
            request=request,
        )

    transport = httpx.MockTransport(handler)
    client = _client(transport)

    case = _make_case(
        "POST",
        expected_status=201,
    )

    record = client.execute(
        case,
        BASE_URL,
        approved=True,
    )

    # 非常重要：
    # POST 即使 Timeout，也不能偷偷再发送一次
    assert attempts == 1

    assert record.actual_status is None
    assert record.transport_error is not None


# ---------------------------------------------------------
# 5. POST 503：不应该 Retry
# ---------------------------------------------------------
def test_post_503_does_not_retry() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            503,
            json={"detail": "service unavailable"},
        )

    transport = httpx.MockTransport(handler)
    client = _client(transport)

    case = _make_case(
        "POST",
        expected_status=201,
    )

    record = client.execute(
        case,
        BASE_URL,
        approved=True,
    )

    # 即使 503 normally retryable，
    # POST 也不能默认自动 Retry
    assert attempts == 1
    assert record.actual_status == 503

def test_get_timeout_uses_exponential_backoff() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts <= 2:
            raise httpx.ReadTimeout(
                "temporary timeout",
                request=request,
            )

        return httpx.Response(
            200,
            json={"ok": True},
        )

    transport = httpx.MockTransport(handler)

    client = LocalHttpClient(
        allowed_ports=frozenset({8001}),
        timeout_seconds=0.1,
        transport=transport,
        max_retries=2,
        retry_backoff_seconds=0.1,
    )

    case = _make_case(
        "GET",
        expected_status=200,
    )

    with patch(
        "testpilot.http_client.sleep"
    ) as mocked_sleep:
        record = client.execute(
            case,
            BASE_URL,
            approved=False,
        )

    assert attempts == 3
    assert record.actual_status == 200

    assert mocked_sleep.call_count == 2

    mocked_sleep.assert_any_call(0.1)
    mocked_sleep.assert_any_call(0.2)

def test_post_timeout_does_not_backoff() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        raise httpx.ReadTimeout(
            "POST timeout",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    client = LocalHttpClient(
        allowed_ports=frozenset({8001}),
        timeout_seconds=0.1,
        transport=transport,
        max_retries=2,
        retry_backoff_seconds=0.1,
    )

    case = _make_case(
        "POST",
        expected_status=201,
    )

    with patch(
        "testpilot.http_client.sleep"
    ) as mocked_sleep:
        record = client.execute(
            case,
            BASE_URL,
            approved=True,
        )

    assert attempts == 1
    assert record.transport_error is not None

    mocked_sleep.assert_not_called()

