from datetime import date

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReceiveItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: int | None = None
    product_name: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    units_per_box: int = Field(default=1, ge=1)
    boxed_units: int = Field(default=0, ge=0)
    unit_price: float = Field(default=0, ge=0)
    box_unit_cost: float = Field(default=0, ge=0)
    scanned_codes: list[str] = Field(default_factory=list)
    serial_number: str = Field(min_length=1, max_length=120)
    batch_number: str = Field(min_length=1, max_length=100)
    manufacturing_date: date
    expiry_date: date
    storage_zone: Literal["AMBIENT", "CHILLED", "FROZEN"]
    temperature_c: float = Field(ge=-80, le=100)


class ReceivePurchaseOrder(BaseModel):
    warehouse_id: int
    items: list[ReceiveItem]