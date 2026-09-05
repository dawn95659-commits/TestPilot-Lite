from __future__ import annotations

import logging
from typing import Any


def configure_logging() -> None:
    """
    TestPilot 的基础日志配置。

    当前先使用简单文本日志。
    后续如果需要，可以升级成 JSON logging /
    OpenTelemetry，而不用修改业务逻辑。
    """
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
    )


def log_event(
    logger: logging.Logger,
    event: str,
    **fields: Any,
) -> None:
    """
    输出统一的 key=value 结构日志。

    示例：
    event=http_retry method=GET attempt=1
    """
    parts = [f"event={event}"]

    for key, value in fields.items():
        if value is None:
            continue

        text = str(value).replace("\n", " ")
        parts.append(f"{key}={text}")

    logger.info(" ".join(parts))
