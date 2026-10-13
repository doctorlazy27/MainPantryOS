from pydantic import BaseModel, Field


class CounterAllocationCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class CheckoutItem(BaseModel):
    scanned_code: str = Field(min_length=1, max_length=120)
    quantity: int = Field(gt=0)


class CheckoutCreate(BaseModel):
    request_key: str | None = Field(default=None, min_length=1, max_length=100)
    items: list[CheckoutItem] = Field(min_length=1)