from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InventoryReceiptDetails(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    serial_number: str = Field(min_length=1, max_length=120)
    batch_number: str = Field(min_length=1, max_length=100)
    manufacturing_date: date
    expiry_date: date
    storage_zone: Literal["AMBIENT", "CHILLED", "FROZEN"] = "AMBIENT"
    temperature_c: float | None = Field(default=None, ge=-80, le=100)
    aisle: str = Field(min_length=1, max_length=50)
    shelf_number: str = Field(min_length=1, max_length=50)