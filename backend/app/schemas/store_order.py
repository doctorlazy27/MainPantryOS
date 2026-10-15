from datetime import datetime

from pydantic import BaseModel, Field


class StoreOrderCreate(BaseModel):
    inventory_id: int
    quantity: int = Field(gt=0)
    needed_by: datetime


class StoreOrderReject(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class CashierCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    cashier_id: str | None = Field(default=None, pattern=r"^\d{10}$")


class CashierLogin(BaseModel):
    cashier_id: str = Field(pattern=r"^\d{10}$")
