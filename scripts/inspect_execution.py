from testpilot.case_generator import generate_test_cases
from testpilot.config import settings
from testpilot.http_client import LocalHttpClient
from testpilot.openapi_parser import parse_openapi
from testpilot.validators import validate_execution


OPENAPI_URL = "http://127.0.0.1:8001/openapi.json"
BASE_URL = "http://127.0.0.1:8001"


def main():
    client = LocalHttpClient(
        allowed_ports=settings.allowed_ports,
        timeout_seconds=settings.timeout_seconds,
    )

    document = client.fetch_openapi(OPENAPI_URL)
    operations = parse_openapi(document)
    cases = generate_test_cases(operations, max_cases=20)

    for case in cases:
        if case.method != "GET":
            continue

        print("=" * 60)
        print("case_id:", case.case_id)
        print("expected_status:", case.expected_status)

        record = client.execute(
            case,
            BASE_URL,
            approved=False,
        )

        print("actual_status:", record.actual_status)
        print("blocked:", record.blocked)
        print("transport_error:", record.transport_error)

        result = validate_execution(case, record)

        print("passed:", result.passed)
        print("schema_valid:", result.schema_valid)
        print("errors:", result.errors)


if __name__ == "__main__":
    main()
