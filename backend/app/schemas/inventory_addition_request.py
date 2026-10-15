from datetime import date

from pydantic import BaseModel, Field


class InventoryAdditionRequestCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    category: str = Field(default="General", min_length=1, max_length=100)
    units_per_box: int = Field(default=1, ge=1)
    boxed_units: int = Field(default=0, ge=0)
    unit_price: float = Field(default=0, ge=0)
    box_unit_cost: float = Field(default=0, ge=0)
