from datetime import date

from pydantic import BaseModel


class BatchCreate(BaseModel):
    product_id: int
    serial_number: str
    batch_number: str
    manufacturing_date: date
    expiry_date: date