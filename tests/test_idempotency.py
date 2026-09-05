from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sample_api.main import (
    IDEMPOTENCY_RECORDS,
    ORDERS,
    app,
)


client = TestClient(app)


@pytest.fixture(autouse=True)
def restore_sample_api_state():
    """
    每个测试结束以后恢复 ORDERS 和 Idempotency Store。

    避免一个测试创建的订单影响下一个测试。
    """

    orders_before = dict(ORDERS)
    idempotency_before = dict(
        IDEMPOTENCY_RECORDS
    )

    yield

    ORDERS.clear()
    ORDERS.update(orders_before)

    IDEMPOTENCY_RECORDS.clear()
    IDEMPOTENCY_RECORDS.update(
        idempotency_before
    )


# ---------------------------------------------------------
# 1. 相同 Key + 相同请求
#
# 应该只创建一次订单
# ---------------------------------------------------------
def test_same_idempotency_key_returns_same_order():
    before_count = len(ORDERS)

    headers = {
        "Idempotency-Key": "test-key-001",
    }

    payload = {
        "product_id": 1,
        "quantity": 1,
    }

    first = client.post(
        "/orders",
        json=payload,
        headers=headers,
    )

    second = client.post(
        "/orders",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201

    # 两次 Response 必须指向同一个订单
    assert (
        first.json()["id"]
        == second.json()["id"]
    )

    # 虽然调用了两次 POST，
    # 但只能真正新增一个订单
    assert len(ORDERS) == before_count + 1


# ---------------------------------------------------------
# 2. 相同 Key + 不同请求
#
# 应该拒绝
# ---------------------------------------------------------
def test_same_key_with_different_payload_is_rejected():
    headers = {
        "Idempotency-Key": "test-key-002",
    }

    first = client.post(
        "/orders",
        json={
            "product_id": 1,
            "quantity": 1,
        },
        headers=headers,
    )

    second = client.post(
        "/orders",
        json={
            "product_id": 1,
            "quantity": 2,
        },
        headers=headers,
    )

    assert first.status_code == 201

    # 同一个 Key 不允许代表两个不同请求
    assert second.status_code == 409


# ---------------------------------------------------------
# 3. 不同 Key + 相同请求
#
# 这是两个独立业务请求，
# 应该创建两个不同订单
# ---------------------------------------------------------
def test_different_idempotency_keys_create_different_orders():
    payload = {
        "product_id": 1,
        "quantity": 1,
    }

    first = client.post(
        "/orders",
        json=payload,
        headers={
            "Idempotency-Key": "test-key-003",
        },
    )

    second = client.post(
        "/orders",
        json=payload,
        headers={
            "Idempotency-Key": "test-key-004",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201

    # Key 不一样，
    # 表示两个独立的业务请求
    assert (
        first.json()["id"]
        != second.json()["id"]
    )
