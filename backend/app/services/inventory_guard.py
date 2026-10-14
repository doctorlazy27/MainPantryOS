from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.batch import Batch


def require_available_batch(db: Session, batch_id: int) -> Batch:
    batch = db.query(Batch).filter(Batch.batch_id == batch_id).with_for_update().first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != "active" or batch.expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="Only active, unexpired batches can be moved or sold")
    return batch