from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
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


app = FastAPI(title="TestPilot Sample Shop API", version="1.0.0")

PRODUCTS = {
    1: Product(id=1, name="Keyboard", price=299.0),
    2: Product(id=2, name="Mouse", price=99.0),
}
ORDERS = {
    1: Order(
        id=1,
        product_id=1,
        quantity=1,
        created_at=datetime.now(timezone.utc),
    )
}


@app.get(
    "/products",
    response_model=list[Product],
    operation_id="list_products",
)
def list_products(max_price: float | None = None) -> list[Product]:
    products = list(PRODUCTS.values())

    if max_price is not None:
        products = [
            product
            for product in products
            if product.price <= max_price
        ]

    return products



@app.get(
    "/products/{product_id}",
    response_model=Product,
    responses={404: {"model": ErrorDetail}},
    operation_id="get_product",
)
def get_product(product_id: int) -> Product:
    product = PRODUCTS.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return product


@app.post(
    "/orders",
    response_model=Order,
    status_code=201,
    responses={400: {"model": ErrorDetail}},
    operation_id="create_order",
)
def create_order(payload: OrderCreate) -> Order:
    if payload.product_id not in PRODUCTS:
        raise HTTPException(status_code=400, detail="product not found")
    order = Order(
        id=max(ORDERS, default=0) + 1,
        product_id=payload.product_id,
        quantity=payload.quantity,
        created_at=datetime.now(timezone.utc),
    )
    ORDERS[order.id] = order
    return order


@app.get(
    "/orders/{order_id}",
    response_model=Order,
    responses={404: {"model": ErrorDetail}},
    operation_id="get_order",
)
def get_order(order_id: int) -> Order:
    order = ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order

