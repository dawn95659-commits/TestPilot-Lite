from __future__ import annotations

import pytest

from testpilot.openapi_parser import OpenAPIError, parse_openapi, resolve_local_refs


def test_parse_operations(openapi_document: dict) -> None:
    operations = parse_openapi(openapi_document)
    assert [item.operation_id for item in operations] == ["list_items", "get_item", "create_order"]


def test_parse_path_parameter(openapi_document: dict) -> None:
    operation = next(item for item in parse_openapi(openapi_document) if item.operation_id == "get_item")
    assert operation.parameters[0].name == "item_id"
    assert operation.parameters[0].required is True
    assert operation.parameters[0].schema_data["type"] == "integer"


def test_resolves_request_body_ref(openapi_document: dict) -> None:
    operation = next(item for item in parse_openapi(openapi_document) if item.operation_id == "create_order")
    assert operation.request_body_required is True
    assert operation.request_body_schema["required"] == ["product_id", "quantity"]


def test_resolves_response_ref(openapi_document: dict) -> None:
    operation = next(item for item in parse_openapi(openapi_document) if item.operation_id == "get_item")
    assert operation.responses["200"]["required"] == ["id", "name"]


def test_rejects_non_openapi() -> None:
    with pytest.raises(OpenAPIError):
        parse_openapi({"paths": {}})


def test_truncates_recursive_ref() -> None:
    document = {"components": {"schemas": {"Node": {"$ref": "#/components/schemas/Node"}}}}
    resolved = resolve_local_refs({"$ref": "#/components/schemas/Node"}, document)
    assert "递归引用" in resolved["description"]

