from __future__ import annotations

import pytest

from testpilot.models import TestCase as APITestCase
from testpilot.security import SecurityError, build_case_url, requires_approval, validate_local_url


PORTS = frozenset({8001})


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8001/openapi.json", "http://localhost:8001/docs"],
)
def test_allows_local_urls(url: str) -> None:
    assert validate_local_url(url, PORTS) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8001/openapi.json",
        "http://example.com:8001/openapi.json",
        "http://127.0.0.1:9000/openapi.json",
        "http://user:pass@127.0.0.1:8001/openapi.json",
        "http://127.0.0.1:8001/openapi.json#secret",
    ],
)
def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(SecurityError):
        validate_local_url(url, PORTS)


def test_write_methods_need_approval() -> None:
    assert not requires_approval("GET")
    assert requires_approval("POST")
    assert requires_approval("DELETE")


def test_build_case_url_encodes_path_parameter() -> None:
    case = APITestCase(
        case_id="one",
        operation_id="get_item",
        title="demo",
        category="happy",
        method="GET",
        path="/items/{item_id}",
        path_params={"item_id": "a/b"},
        expected_status=200,
    )
    assert build_case_url("http://127.0.0.1:8001", case).endswith("/items/a%2Fb")


def test_build_case_url_rejects_missing_parameter() -> None:
    case = APITestCase(
        case_id="one",
        operation_id="get_item",
        title="demo",
        category="happy",
        method="GET",
        path="/items/{item_id}",
        expected_status=200,
    )
    with pytest.raises(SecurityError):
        build_case_url("http://127.0.0.1:8001", case)
