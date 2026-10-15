from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.activity_log import ActivityLog
from app.models.user import User


router = APIRouter(
    prefix="/activity",
    tags=["Activity"]
)


@router.get("/")
def get_activity(
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("view_activity")
    )
):
    logs = (
            db.query(ActivityLog)
            .outerjoin(User, ActivityLog.user_id == User.user_id)
            .filter(User.warehouse_id == current_user.get("warehouse_id"))
        .order_by(ActivityLog.created_at.desc())
        .all()
    )

    return {
        "activity": logs
    }