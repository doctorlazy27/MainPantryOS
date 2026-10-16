from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class BatchCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: int
    serial_number: str = Field(min_length=1, max_length=120)
    batch_number: str = Field(min_length=1, max_length=100)
    manufacturing_date: date
    expiry_date: date