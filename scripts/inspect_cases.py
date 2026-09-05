import httpx

from testpilot.openapi_parser import parse_openapi
from testpilot.case_generator import generate_test_cases


document = httpx.get(
    "http://127.0.0.1:8001/openapi.json"
).json()

operations = parse_openapi(document)

cases = generate_test_cases(
    operations,
    max_cases=20,
)

for case in cases:
    print("=" * 70)
    print("case_id:", case.case_id)
    print("operation_id:", case.operation_id)
    print("category:", case.category)
    print("method:", case.method)
    print("path:", case.path)
    print("path_params:", case.path_params)
    print("query_params:", case.query_params)
    print("json_body:", case.json_body)
    print("expected_status:", case.expected_status)
    print("needs_approval:", case.needs_approval)
