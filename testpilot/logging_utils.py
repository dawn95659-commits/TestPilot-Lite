from __future__ import annotations

import json
import logging
from typing import Any


# =========================================================
# Logging configuration
# =========================================================

DEFAULT_LOG_FORMAT = (
    "%(asctime)s "
    "%(levelname)s "
    "%(name)s "
    "%(message)s"
)


def configure_logging(
    level: int = logging.INFO,
) -> None:
    """
    配置 TestPilot 基础日志。

    当前采用：
        timestamp
        level
        logger name
        key=value structured message

    示例：

        2026-09-05 12:00:00 INFO testpilot.http_client
        event=http_retry method=GET attempt=1 reason=ReadTimeout

    后续如果升级到：
        JSON Logging
        OpenTelemetry
        Loki
        ELK

    业务代码中的 log_event() 调用基本不需要修改。
    """
    logging.basicConfig(
        level=level,
        format=DEFAULT_LOG_FORMAT,
    )


# =========================================================
# Value formatting
# =========================================================

def _format_value(value: Any) -> str:
    """
    把日志字段统一转换成单行字符串。

    dict / list 等复杂对象使用 JSON，
    避免日志难以阅读。

    换行符会被替换，保证一个 Event 尽量只占一行。
    """
    if isinstance(
        value,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        try:
            value = json.dumps(
                value,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            value = str(value)
    else:
        value = str(value)

    return (
        value
        .replace("\r", " ")
        .replace("\n", " ")
    )


# =========================================================
# Structured event logging
# =========================================================

def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """
    输出统一的 key=value 结构日志。

    示例：

        log_event(
            logger,
            "http_retry",
            method="GET",
            url="http://127.0.0.1:8001/products",
            attempt=1,
            reason="ReadTimeout",
        )

    输出类似：

        event=http_retry
        method=GET
        url=http://127.0.0.1:8001/products
        attempt=1
        reason=ReadTimeout

    实际日志会保持在同一行。

    如果需要不同日志等级：

        log_event(
            logger,
            "http_retry",
            level=logging.WARNING,
            method="GET",
            attempt=1,
        )
    """
    parts = [
        f"event={_format_value(event)}",
    ]

    for key, value in fields.items():
        if value is None:
            continue

        parts.append(
            f"{key}={_format_value(value)}"
        )

    logger.log(
        level,
        " ".join(parts),
    )
