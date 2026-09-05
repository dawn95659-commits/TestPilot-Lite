from __future__ import annotations

from time import perf_counter, sleep
from typing import Any

import httpx

from .models import ExecutionRecord, TestCase
from .security import (
    SecurityError,
    build_case_url,
    validate_local_url,
)


# =========================================================
# Retry Policy
# =========================================================

# 默认允许自动重试的“读取型”请求。
# 写操作默认不自动重试，避免重复创建 / 修改数据。
SAFE_RETRY_METHODS = frozenset(
    {
        "GET",
        "HEAD",
        "OPTIONS",
    }
)


# 通常表示临时服务故障，可以考虑稍后重试。
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
    # Client
    # =====================================================

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        )

    # =====================================================
    # Retry helpers
    # =====================================================

    @staticmethod
    def _can_retry_method(
        method: str,
    ) -> bool:
        """
        判断 HTTP Method 是否允许默认自动重试。

        当前策略：

        GET      -> 可以
        HEAD     -> 可以
        OPTIONS  -> 可以

        POST     -> 不可以
        PUT      -> 不可以
        PATCH    -> 不可以
        DELETE   -> 不可以
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
        判断响应状态码是否属于临时故障。
        """
        return (
            status_code
            in RETRYABLE_STATUS_CODES
        )

    def _sleep_before_retry(
        self,
        retry_index: int,
    ) -> None:
        """
        Exponential Backoff：

        retry_backoff_seconds = 0.1 时：

        第 1 次 Retry：
            0.1 * 2^0 = 0.1 秒

        第 2 次 Retry：
            0.1 * 2^1 = 0.2 秒

        第 3 次 Retry：
            0.1 * 2^2 = 0.4 秒
        """
        if self.retry_backoff_seconds == 0:
            return

        delay = (
            self.retry_backoff_seconds
            * (2 ** retry_index)
        )

        sleep(delay)

    def _request_with_retry(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        HTTP 请求 + Safe Retry Policy。

        Retry 必须同时满足：

        1. Method 可以安全 Retry
        2. 错误属于临时故障
        3. 还有剩余 Retry 次数


        例如：

        GET + Timeout
            -> Retry

        GET + 503
            -> Retry

        GET + 404
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

        # max_retries 表示“额外重试次数”。
        #
        # max_retries = 2：
        #
        # 第 1 次原始请求
        # 第 2 次 retry
        # 第 3 次 retry
        #
        # 总共最多 3 次。
        total_attempts = (
            self.max_retries + 1
            if retry_allowed
            else 1
        )

        for attempt in range(total_attempts):
            try:
                response = client.request(
                    method,
                    url,
                    **kwargs,
                )

            except httpx.TransportError:
                # -----------------------------------------
                # Timeout / ConnectError / ProtocolError
                # 等 Transport 层错误
                # -----------------------------------------

                has_more_attempts = (
                    attempt
                    < total_attempts - 1
                )

                if not has_more_attempts:
                    raise

                # 当前 method 一定是 safe method，
                # 因为非 safe method 的 total_attempts=1。
                self._sleep_before_retry(
                    attempt
                )

                continue

            # ---------------------------------------------
            # HTTP 已经收到响应，但服务暂时不可用
            # ---------------------------------------------

            has_more_attempts = (
                attempt
                < total_attempts - 1
            )

            if (
                retry_allowed
                and self._can_retry_status(
                    response.status_code
                )
                and has_more_attempts
            ):
                # 当前 Response 后续不再使用。
                response.close()

                self._sleep_before_retry(
                    attempt
                )

                continue

            # ---------------------------------------------
            # 正常返回
            #
            # 这里包括：
            #
            # 200 / 201
            # 404
            # 405
            # 422
            #
            # 也包括：
            # 已经耗尽 Retry 后的 502/503/504
            # ---------------------------------------------

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

        # 如果重试全部结束后还是：
        #
        # 404 / 500 / 503 ...
        #
        # OpenAPI 获取就是失败。
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

        if not isinstance(payload, dict):
            raise ValueError(
                "OpenAPI 响应必须是 JSON object"
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
            # 请求时间
            # +
            # Retry 时间
            # +
            # Backoff 时间
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
                # 接口返回 HTML / text/plain 等内容时，
                # HTTP 请求本身仍然可能成功。
                #
                # 所以这里不当 TransportError，
                # 而是保存 response_text，
                # 后续交给 Validator 判断。
                response_json = None

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
            return ExecutionRecord(
                case_id=case.case_id,
                transport_error=str(exc),
            )
