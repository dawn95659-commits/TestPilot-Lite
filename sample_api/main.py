from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    detail: str


class Product(BaseModel):
    id: int
    name: str
    price: float


class OrderCreate(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)


class Order(BaseModel):
    id: int
    product_id: int
    quantity: int
    created_at: datetime


app = FastAPI(
    title="TestPilot Sample Shop API",
    version="1.0.0",
)


PRODUCTS = {
    1: Product(
        id=1,
        name="Keyboard",
        price=299.0,
    ),
    2: Product(
        id=2,
        name="Mouse",
        price=99.0,
    ),
}


ORDERS = {
    1: Order(
        id=1,
        product_id=1,
        quantity=1,
        created_at=datetime.now(timezone.utc),
    )
}


# ---------------------------------------------------------
# Idempotency Store
#
# key:
#   Idempotency-Key
#
# value:
#   (
#       第一次请求的 payload,
#       第一次创建的 order_id
#   )
#
# 这是 Demo 用的内存实现。
# 真正生产系统一般会放到 Redis / Database。
# ---------------------------------------------------------
IDEMPOTENCY_RECORDS: dict[
    str,
    tuple[dict[str, int], int],
] = {}


@app.get(
    "/products",
    response_model=list[Product],
    operation_id="list_products",
)
def list_products() -> list[Product]:
    return list(PRODUCTS.values())


@app.get(
    "/products/{product_id}",
    response_model=Product,
    responses={
        404: {
            "model": ErrorDetail,
        }
    },
    operation_id="get_product",
)
def get_product(
    product_id: int,
) -> Product:
    product = PRODUCTS.get(product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="product not found",
        )

    return product


@app.post(
    "/orders",
    response_model=Order,
    status_code=201,
    responses={
        400: {
            "model": ErrorDetail,
        },
        409: {
            "model": ErrorDetail,
        },
    },
    operation_id="create_order",
)
def create_order(
    payload: OrderCreate,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
) -> Order:
    """
    创建订单。

    Idempotency 规则：

    1. 没有 Idempotency-Key
       → 正常创建订单。

    2. 第一次使用某个 Key
       → 创建订单并保存结果。

    3. 相同 Key + 相同 payload
       → 不再创建新订单，
         直接返回第一次创建的订单。

    4. 相同 Key + 不同 payload
       → 返回 409 Conflict。
    """

    payload_data = payload.model_dump()

    # -----------------------------------------------------
    # 1. 检查 Idempotency-Key 是否已经使用过
    # -----------------------------------------------------
    if idempotency_key is not None:
        existing = IDEMPOTENCY_RECORDS.get(
            idempotency_key
        )

        if existing is not None:
            (
                previous_payload,
                previous_order_id,
            ) = existing

            # -------------------------------------------------
            # 同一个 Key，却发送不同请求
            # -------------------------------------------------
            if previous_payload != payload_data:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Idempotency-Key 已被用于"
                        "不同的请求内容"
                    ),
                )

            # -------------------------------------------------
            # 同一个 Key + 同一个请求
            #
            # 不再创建新订单，
            # 返回第一次创建的订单。
            # -------------------------------------------------
            previous_order = ORDERS.get(
                previous_order_id
            )

            if previous_order is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Idempotency-Key 对应的"
                        "历史订单不存在"
                    ),
                )

            return previous_order

    # -----------------------------------------------------
    # 2. 正常业务校验
    # -----------------------------------------------------
    if payload.product_id not in PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail="product not found",
        )

    # -----------------------------------------------------
    # 3. 真正创建订单
    # -----------------------------------------------------
    order = Order(
        id=max(ORDERS, default=0) + 1,
        product_id=payload.product_id,
        quantity=payload.quantity,
        created_at=datetime.now(timezone.utc),
    )

    ORDERS[order.id] = order

    # -----------------------------------------------------
    # 4. 如果带了 Key，记录第一次执行结果
    # -----------------------------------------------------
    if idempotency_key is not None:
        IDEMPOTENCY_RECORDS[
            idempotency_key
        ] = (
            payload_data,
            order.id,
        )

    return order


@app.get(
    "/orders/{order_id}",
    response_model=Order,
    responses={
        404: {
            "model": ErrorDetail,
        }
    },
    operation_id="get_order",
)
def get_order(
    order_id: int,
) -> Order:
    order = ORDERS.get(order_id)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="order not found",
        )

    return order
