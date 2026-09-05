from __future__ import annotations

import logging
from time import perf_counter, sleep
from typing import Any

import httpx

from .logging_utils import log_event
from .models import ExecutionRecord, TestCase
from .security import (
    SecurityError,
    build_case_url,
    validate_local_url,
)


logger = logging.getLogger(__name__)


# =========================================================
# Retry Policy
# =========================================================

# 默认只允许读取型请求自动重试。
#
# POST / PUT / PATCH / DELETE 默认不 Retry，
# 避免因为网络异常导致重复写入。
SAFE_RETRY_METHODS = frozenset(
    {
        "GET",
        "HEAD",
        "OPTIONS",
    }
)


# 这些状态通常表示临时服务故障，
# Safe Method 可以考虑自动 Retry。
RETRYABLE_STATUS_CODES = frozenset(
    {
        502,  # Bad Gateway
        503,  # Service Unavailable
        504,  # Gateway Timeout
    }
)


class LocalHttpClient:
    def __init__(
        self,
        allowed_ports: frozenset[int],
        timeout_seconds: float = 3.0,
        transport: httpx.BaseTransport | None = None,
        max_openapi_bytes: int = 1_000_000,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.1,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds 必须大于 0"
            )

        if max_openapi_bytes <= 0:
            raise ValueError(
                "max_openapi_bytes 必须大于 0"
            )

        if max_retries < 0:
            raise ValueError(
                "max_retries 不能小于 0"
            )

        if retry_backoff_seconds < 0:
            raise ValueError(
                "retry_backoff_seconds 不能小于 0"
            )

        self.allowed_ports = allowed_ports
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.max_openapi_bytes = max_openapi_bytes
        self.max_retries = max_retries
        self.retry_backoff_seconds = (
            retry_backoff_seconds
        )

    # =====================================================
    # HTTPX Client
    # =====================================================

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        )

    # =====================================================
    # Retry Policy Helpers
    # =====================================================

    @staticmethod
    def _can_retry_method(
        method: str,
    ) -> bool:
        """
        当前允许自动 Retry 的 HTTP Method：

        GET
        HEAD
        OPTIONS
        """
        return (
            method.upper()
            in SAFE_RETRY_METHODS
        )

    @staticmethod
    def _can_retry_status(
        status_code: int,
    ) -> bool:
        """
        当前允许 Retry 的临时 HTTP Status：

        502
        503
        504
        """
        return (
            status_code
            in RETRYABLE_STATUS_CODES
        )

    def _retry_delay_seconds(
        self,
        retry_index: int,
    ) -> float:
        """
        Exponential Backoff。

        retry_backoff_seconds = 0.1 时：

        Retry #1
        -> 0.1 秒

        Retry #2
        -> 0.2 秒

        Retry #3
        -> 0.4 秒
        """
        return (
            self.retry_backoff_seconds
            * (2 ** retry_index)
        )

    def _sleep_before_retry(
        self,
        retry_index: int,
    ) -> None:
        delay = self._retry_delay_seconds(
            retry_index
        )

        if delay <= 0:
            return

        sleep(delay)

    # =====================================================
    # HTTP Request + Retry
    # =====================================================

    def _request_with_retry(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Safe Retry Policy。

        Retry 必须同时满足：

        1. HTTP Method 允许安全 Retry
        2. Failure 属于临时故障
        3. 还有剩余 Retry 次数


        Examples
        --------

        GET + Timeout
        -> Retry

        GET + ConnectError
        -> Retry

        GET + 503
        -> Retry

        GET + 404
        -> 不 Retry

        GET + 422
        -> 不 Retry

        POST + Timeout
        -> 不 Retry

        POST + 503
        -> 不 Retry
        """

        method = method.upper()

        retry_allowed = (
            self._can_retry_method(method)
        )

        # max_retries 表示额外 Retry 次数。
        #
        # max_retries = 2：
        #
        # Request #1
        # Retry   #1
        # Retry   #2
        #
        # 最多共请求 3 次。
        total_attempts = (
            self.max_retries + 1
            if retry_allowed
            else 1
        )

        for attempt_index in range(
            total_attempts
        ):
            request_number = (
                attempt_index + 1
            )

            # -------------------------------------------------
            # Transport Layer
            # -------------------------------------------------

            try:
                response = client.request(
                    method,
                    url,
                    **kwargs,
                )

            except httpx.TransportError as exc:
                has_more_attempts = (
                    attempt_index
                    < total_attempts - 1
                )

                # 已经没有 Retry 机会。
                if not has_more_attempts:
                    log_event(
                        logger,
                        "http_retry_exhausted",
                        method=method,
                        url=url,
                        attempt=request_number,
                        max_attempts=total_attempts,
                        reason=type(exc).__name__,
                    )

                    raise

                delay = (
                    self._retry_delay_seconds(
                        attempt_index
                    )
                )

                log_event(
                    logger,
                    "http_retry",
                    method=method,
                    url=url,
                    attempt=request_number,
                    next_attempt=(
                        request_number + 1
                    ),
                    max_attempts=total_attempts,
                    reason=type(exc).__name__,
                    retry_in_seconds=delay,
                )

                self._sleep_before_retry(
                    attempt_index
                )

                continue

            # -------------------------------------------------
            # HTTP Response Received
            # -------------------------------------------------

            has_more_attempts = (
                attempt_index
                < total_attempts - 1
            )

            # GET / HEAD / OPTIONS 收到
            # 502 / 503 / 504 时可以 Retry。
            if (
                retry_allowed
                and self._can_retry_status(
                    response.status_code
                )
                and has_more_attempts
            ):
                delay = (
                    self._retry_delay_seconds(
                        attempt_index
                    )
                )

                log_event(
                    logger,
                    "http_retry",
                    method=method,
                    url=url,
                    attempt=request_number,
                    next_attempt=(
                        request_number + 1
                    ),
                    max_attempts=total_attempts,
                    reason=(
                        f"status_"
                        f"{response.status_code}"
                    ),
                    status_code=(
                        response.status_code
                    ),
                    retry_in_seconds=delay,
                )

                # 当前 Response 后续不用了。
                response.close()

                self._sleep_before_retry(
                    attempt_index
                )

                continue

            # -------------------------------------------------
            # Retryable Status 已经耗尽次数
            # -------------------------------------------------

            if (
                retry_allowed
                and self._can_retry_status(
                    response.status_code
                )
                and not has_more_attempts
            ):
                log_event(
                    logger,
                    "http_retry_exhausted",
                    method=method,
                    url=url,
                    attempt=request_number,
                    max_attempts=total_attempts,
                    reason=(
                        f"status_"
                        f"{response.status_code}"
                    ),
                    status_code=(
                        response.status_code
                    ),
                )

            # -------------------------------------------------
            # 最终 Response
            # -------------------------------------------------
            #
            # 包括：
            #
            # 200 / 201
            # 404
            # 405
            # 409
            # 422
            #
            # 也包括已经耗尽 Retry 的：
            # 502 / 503 / 504
            #
            # 注意：
            # 404 / 422 并不等于 TestCase Failed。
            # Validator 会根据 expected_status 判断。
            # -------------------------------------------------

            return response

        # 理论上不会执行到这里。
        raise RuntimeError(
            "HTTP retry loop unexpectedly exhausted"
        )

    # =====================================================
    # OpenAPI
    # =====================================================

    def fetch_openapi(
        self,
        url: str,
    ) -> dict[str, Any]:
        started = perf_counter()

        try:
            validate_local_url(
                url,
                self.allowed_ports,
            )

            with self._client() as client:
                response = (
                    self._request_with_retry(
                        client,
                        "GET",
                        url,
                        headers={
                            "Accept":
                            "application/json",
                        },
                    )
                )

            response.raise_for_status()

            if (
                len(response.content)
                > self.max_openapi_bytes
            ):
                raise ValueError(
                    "OpenAPI 文档超过大小限制："
                    f"{self.max_openapi_bytes} bytes"
                )

            try:
                payload = response.json()

            except ValueError as exc:
                raise ValueError(
                    "OpenAPI 响应不是合法 JSON"
                ) from exc

            if not isinstance(
                payload,
                dict,
            ):
                raise ValueError(
                    "OpenAPI 响应必须是 JSON object"
                )

        except (
            httpx.HTTPError,
            SecurityError,
            ValueError,
        ) as exc:
            latency_ms = (
                perf_counter() - started
            ) * 1000

            log_event(
                logger,
                "openapi_fetch_failed",
                url=url,
                latency_ms=round(
                    latency_ms,
                    2,
                ),
                error_type=type(exc).__name__,
                error=str(exc),
            )

            raise

        latency_ms = (
            perf_counter() - started
        ) * 1000

        log_event(
            logger,
            "openapi_fetch_success",
            url=url,
            status_code=response.status_code,
            bytes=len(response.content),
            latency_ms=round(
                latency_ms,
                2,
            ),
        )

        return payload

    # =====================================================
    # Execute TestCase
    # =====================================================

    def execute(
        self,
        case: TestCase,
        base_url: str,
        approved: bool,
    ) -> ExecutionRecord:
        validate_local_url(
            base_url,
            self.allowed_ports,
        )

        # -------------------------------------------------
        # Human-in-the-loop
        # -------------------------------------------------

        if (
            case.needs_approval
            and not approved
        ):
            log_event(
                logger,
                "test_case_blocked",
                case_id=case.case_id,
                method=case.method,
                path=case.path,
                reason="approval_required",
            )

            return ExecutionRecord(
                case_id=case.case_id,
                blocked=True,
                response_text=(
                    "写操作未获人工批准，已拦截"
                ),
            )

        try:
            url = build_case_url(
                base_url,
                case,
            )

            # latency 包含：
            #
            # HTTP Request
            # +
            # Retry
            # +
            # Exponential Backoff
            started = perf_counter()

            with self._client() as client:
                response = (
                    self._request_with_retry(
                        client,
                        case.method,
                        url,
                        params=(
                            case.query_params
                        ),
                        json=case.json_body,
                        headers={
                            "Accept":
                            "application/json",
                        },
                    )
                )

            latency_ms = (
                perf_counter() - started
            ) * 1000

            # -------------------------------------------------
            # Response JSON
            # -------------------------------------------------

            try:
                response_json: Any | None = (
                    response.json()
                )

            except ValueError:
                # 返回 HTML / text/plain 等内容，
                # 不属于 Transport Error。
                #
                # 保存原始文本，
                # 后续由 Validator 判断。
                response_json = None

            log_event(
                logger,
                "test_case_http_result",
                case_id=case.case_id,
                method=case.method,
                path=case.path,
                status_code=(
                    response.status_code
                ),
                latency_ms=round(
                    latency_ms,
                    2,
                ),
                response_is_json=(
                    response_json
                    is not None
                ),
            )

            return ExecutionRecord(
                case_id=case.case_id,
                actual_status=(
                    response.status_code
                ),
                latency_ms=latency_ms,
                response_json=response_json,
                response_text=(
                    response.text[:2000]
                ),
            )

        except (
            httpx.HTTPError,
            SecurityError,
            ValueError,
        ) as exc:
            log_event(
                logger,
                "test_case_transport_error",
                case_id=case.case_id,
                method=case.method,
                path=case.path,
                error_type=(
                    type(exc).__name__
                ),
                error=str(exc),
            )

            return ExecutionRecord(
                case_id=case.case_id,
                transport_error=str(exc),
            )
