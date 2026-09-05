from __future__ import annotations

from typing import Any

from .models import OperationSpec, ParameterSpec, TestCase
from .security import requires_approval


def _example_for_name(name: str, schema: dict[str, Any]) -> Any:
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]

    value_type = schema.get("type")
    lowered = name.lower()

    if value_type == "integer":
        return max(int(schema.get("minimum", 1)), 1)

    if value_type == "number":
        return max(float(schema.get("minimum", 1.0)), 1.0)

    if value_type == "boolean":
        return True

    if value_type == "array":
        return [_build_example(schema.get("items", {}), name)]

    if value_type == "object" or "properties" in schema:
        return _build_example(schema, name)

    if "email" in lowered:
        return "demo@example.com"

    if "sku" in lowered:
        return "SKU-001"

    if "name" in lowered or "title" in lowered:
        return "demo"

    return "test"


def _build_example(
    schema: dict[str, Any],
    name: str = "value",
) -> Any:
    if "example" in schema:
        return schema["example"]

    if "default" in schema:
        return schema["default"]

    if schema.get("enum"):
        return schema["enum"][0]

    if schema.get("type") == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        selected = required or set(properties)

        return {
            key: _example_for_name(
                key,
                properties.get(key, {}),
            )
            for key in properties
            if key in selected
        }

    return _example_for_name(name, schema)


def _build_below_minimum_body(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], str, int | float] | None:
    """
    找到请求体中第一个带 minimum 约束的必填数字字段，
    并生成一个比 minimum 小 1 的非法请求体。

    第一版只处理：
    - 顶层 object
    - required 字段
    - integer / number
    - minimum
    """
    if not schema:
        return None

    if schema.get("type") != "object" and "properties" not in schema:
        return None

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    normal_body = _build_example(schema)

    if not isinstance(normal_body, dict):
        return None

    for field_name, field_schema in properties.items():
        # 第一版只处理必填字段
        if field_name not in required:
            continue

        value_type = field_schema.get("type")
        minimum = field_schema.get("minimum")

        if minimum is None:
            continue

        if value_type not in {"integer", "number"}:
            continue

        invalid_body = dict(normal_body)

        if value_type == "integer":
            invalid_body[field_name] = int(minimum) - 1
        else:
            invalid_body[field_name] = float(minimum) - 1.0

        return invalid_body, field_name, minimum

    return None


def _parameter_value(
    parameter: ParameterSpec,
    not_found: bool = False,
) -> Any:
    if (
        not_found
        and parameter.schema_data.get("type")
        in {"integer", "number"}
    ):
        return 999999

    return _example_for_name(
        parameter.name,
        parameter.schema_data,
    )


def _success_status(operation: OperationSpec) -> int:
    statuses = sorted(
        int(status)
        for status in operation.responses
        if status.isdigit()
        and 200 <= int(status) < 300
    )

    return statuses[0] if statuses else 200


def generate_test_cases(
    operations: list[OperationSpec],
    max_cases: int = 12,
) -> list[TestCase]:
    cases: list[TestCase] = []

    for operation in operations:
        if len(cases) >= max_cases:
            break

        path_params = {
            item.name: _parameter_value(item)
            for item in operation.parameters
            if item.location == "path"
        }

        query_params = {
            item.name: _parameter_value(item)
            for item in operation.parameters
            if item.location == "query"
            and item.required
        }

        status = _success_status(operation)

        # -------------------------------------------------
        # 1. Happy Case
        # -------------------------------------------------
        cases.append(
            TestCase(
                case_id=f"{operation.operation_id}-happy",
                operation_id=operation.operation_id,
                title=(
                    f"{operation.summary or operation.operation_id}"
                    "：正常请求"
                ),
                category="happy",
                method=operation.method,
                path=operation.path,
                path_params=path_params,
                query_params=query_params,
                json_body=(
                    _build_example(
                        operation.request_body_schema
                    )
                    if operation.request_body_schema
                    else None
                ),
                expected_status=status,
                expected_schema=operation.responses.get(
                    str(status)
                ),
                needs_approval=requires_approval(
                    operation.method
                ),
            )
        )

        if len(cases) >= max_cases:
            break

        path_parameters = [
            p
            for p in operation.parameters
            if p.location == "path"
        ]

        # -------------------------------------------------
        # 2. GET Resource Not Found
        # -------------------------------------------------
        if (
            operation.method == "GET"
            and path_parameters
            and "404" in operation.responses
        ):
            cases.append(
                TestCase(
                    case_id=(
                        f"{operation.operation_id}-not-found"
                    ),
                    operation_id=operation.operation_id,
                    title=(
                        f"{operation.summary or operation.operation_id}"
                        "：资源不存在"
                    ),
                    category="boundary",
                    method=operation.method,
                    path=operation.path,
                    path_params={
                        p.name: _parameter_value(
                            p,
                            not_found=True,
                        )
                        for p in path_parameters
                    },
                    expected_status=404,
                    expected_schema=(
                        operation.responses.get("404")
                    ),
                    needs_approval=False,
                )
            )

        if len(cases) >= max_cases:
            break

        # -------------------------------------------------
        # 3. Missing Request Body
        # -------------------------------------------------
        if operation.request_body_required:
            cases.append(
                TestCase(
                    case_id=(
                        f"{operation.operation_id}-missing-body"
                    ),
                    operation_id=operation.operation_id,
                    title=(
                        f"{operation.summary or operation.operation_id}"
                        "：缺少请求体"
                    ),
                    category="negative",
                    method=operation.method,
                    path=operation.path,
                    path_params=path_params,
                    query_params=query_params,
                    json_body=None,
                    expected_status=422,
                    expected_schema=(
                        operation.responses.get("422")
                    ),
                    needs_approval=requires_approval(
                        operation.method
                    ),
                )
            )

        # -------------------------------------------------
        # 4. Invalid Path Parameter Type
        # -------------------------------------------------
        elif (
            path_parameters
            and path_parameters[0]
            .schema_data.get("type")
            in {"integer", "number"}
        ):
            invalid = dict(path_params)

            invalid[
                path_parameters[0].name
            ] = "not-a-number"

            cases.append(
                TestCase(
                    case_id=(
                        f"{operation.operation_id}-invalid-path"
                    ),
                    operation_id=operation.operation_id,
                    title=(
                        f"{operation.summary or operation.operation_id}"
                        "：路径参数类型错误"
                    ),
                    category="negative",
                    method=operation.method,
                    path=operation.path,
                    path_params=invalid,
                    expected_status=422,
                    expected_schema=(
                        operation.responses.get("422")
                    ),
                    needs_approval=requires_approval(
                        operation.method
                    ),
                )
            )

        if len(cases) >= max_cases:
            break

        # -------------------------------------------------
        # 5. NEW: Request Body Below Minimum
        # -------------------------------------------------
        if (
            operation.request_body_schema
            and "422" in operation.responses
        ):
            violation = _build_below_minimum_body(
                operation.request_body_schema
            )

            if violation is not None:
                (
                    invalid_body,
                    field_name,
                    minimum,
                ) = violation

                cases.append(
                    TestCase(
                        case_id=(
                            f"{operation.operation_id}"
                            f"-below-minimum-{field_name}"
                        ),
                        operation_id=operation.operation_id,
                        title=(
                            f"{operation.summary or operation.operation_id}"
                            f"：{field_name} 低于最小值 {minimum}"
                        ),
                        category="boundary",
                        method=operation.method,
                        path=operation.path,
                        path_params=path_params,
                        query_params=query_params,
                        json_body=invalid_body,
                        expected_status=422,
                        expected_schema=(
                            operation.responses.get("422")
                        ),
                        needs_approval=requires_approval(
                            operation.method
                        ),
                    )
                )

    return cases[:max_cases]
