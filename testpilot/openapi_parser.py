from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import OperationSpec, ParameterSpec


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


class OpenAPIError(ValueError):
    """Raised when an OpenAPI document cannot be inspected safely."""


def _lookup_ref(document: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise OpenAPIError("当前版本只支持 OpenAPI 文档内的 $ref")
    value: Any = document
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            raise OpenAPIError(f"无法解析 $ref: {ref}")
        value = value[key]
    return value


def resolve_local_refs(
    value: Any,
    document: dict[str, Any],
    seen: frozenset[str] = frozenset(),
) -> Any:
    if isinstance(value, list):
        return [resolve_local_refs(item, document, seen) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if ref in seen:
            return {"type": "object", "description": f"递归引用已截断: {ref}"}
        resolved = deepcopy(_lookup_ref(document, ref))
        merged = {**resolved, **{k: v for k, v in value.items() if k != "$ref"}}
        return resolve_local_refs(merged, document, seen | {ref})
    return {key: resolve_local_refs(item, document, seen) for key, item in value.items()}


def _json_schema(content: dict[str, Any] | None, document: dict[str, Any]) -> dict[str, Any] | None:
    if not content:
        return None
    media = content.get("application/json")
    if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
        return None
    return resolve_local_refs(media["schema"], document)


def parse_openapi(document: dict[str, Any]) -> list[OperationSpec]:
    if not isinstance(document, dict) or "openapi" not in document:
        raise OpenAPIError("文件不是有效的 OpenAPI 3 文档")
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise OpenAPIError("OpenAPI 文档中没有 paths")

    operations: list[OperationSpec] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        shared_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            raw_parameters = [*shared_parameters, *operation.get("parameters", [])]
            parameters: list[ParameterSpec] = []
            for raw in raw_parameters:
                raw = resolve_local_refs(raw, document)
                if not isinstance(raw, dict) or raw.get("in") not in {"path", "query", "header", "cookie"}:
                    continue
                parameters.append(
                    ParameterSpec(
                        name=raw.get("name", "unknown"),
                        location=raw["in"],
                        required=bool(raw.get("required", False)),
                        schema_data=resolve_local_refs(raw.get("schema", {}), document),
                    )
                )

            request_body = resolve_local_refs(operation.get("requestBody", {}), document)
            request_schema = _json_schema(request_body.get("content"), document) if request_body else None

            responses: dict[str, dict[str, Any] | None] = {}
            for status, response in operation.get("responses", {}).items():
                response = resolve_local_refs(response, document)
                responses[str(status)] = _json_schema(response.get("content"), document)

            operation_id = operation.get("operationId") or f"{method}_{path}".replace("/", "_")
            operations.append(
                OperationSpec(
                    operation_id=operation_id,
                    method=method.upper(),
                    path=path,
                    summary=operation.get("summary", ""),
                    parameters=parameters,
                    request_body_schema=request_schema,
                    request_body_required=bool(request_body.get("required", False)) if request_body else False,
                    responses=responses,
                )
            )

    if not operations:
        raise OpenAPIError("没有解析到可测试的 HTTP operation")
    return operations

