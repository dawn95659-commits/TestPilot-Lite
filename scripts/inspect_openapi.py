import httpx

from testpilot.openapi_parser import parse_openapi


document = httpx.get(
    "http://127.0.0.1:8001/openapi.json"
).json()

operations = parse_openapi(document)

for op in operations:
    print("=" * 60)
    print("operation_id:", op.operation_id)
    print("method:", op.method)
    print("path:", op.path)
    print("parameters:", op.parameters)
    print("request_body_schema:", op.request_body_schema)
    print("responses:", op.responses)
