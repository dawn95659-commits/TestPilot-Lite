from __future__ import annotations

from urllib.parse import quote, urljoin, urlparse

from .models import TestCase


LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class SecurityError(ValueError):
    """Raised when a target violates the local-only execution policy."""


def validate_local_url(url: str, allowed_ports: frozenset[int]) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise SecurityError("只允许使用 http 访问本地测试服务")
    if parsed.hostname not in LOCAL_HOSTS:
        raise SecurityError("只允许 localhost、127.0.0.1 或 ::1")
    if parsed.username or parsed.password:
        raise SecurityError("URL 中不允许包含用户名或密码")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SecurityError("端口格式非法") from exc
    if port is None or port not in allowed_ports:
        raise SecurityError(f"端口必须在白名单中：{sorted(allowed_ports)}")
    if parsed.fragment:
        raise SecurityError("URL 中不允许包含 fragment")
    return url


def base_url_from_openapi_url(url: str) -> str:
    parsed = urlparse(url)
    host = f"[{parsed.hostname}]" if ":" in (parsed.hostname or "") else parsed.hostname
    return f"{parsed.scheme}://{host}:{parsed.port}"


def build_case_url(base_url: str, case: TestCase) -> str:
    path = case.path
    for name, value in case.path_params.items():
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    if "{" in path or "}" in path:
        raise SecurityError("路径参数不完整")
    if not path.startswith("/") or "://" in path or path.startswith("//"):
        raise SecurityError("OpenAPI 路径非法")
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def requires_approval(method: str) -> bool:
    return method.upper() not in SAFE_METHODS

