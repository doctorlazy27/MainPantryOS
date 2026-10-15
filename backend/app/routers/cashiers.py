from collections import defaultdict, deque
from secrets import randbelow, token_urlsafe
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.auth.roles import UserRole
from app.auth.security import create_access_token, hash_password
from app.database import get_db
from app.models.auth_session import AuthSession
from app.models.counter_sale import CounterSale
from app.models.user import User
from app.routers.users import remove_user
from app.schemas.store_order import CashierCreate, CashierLogin
from app.services.activity import log_activity

router = APIRouter(tags=["Cashiers"])

_FAILURE_WINDOW_SECONDS = 15 * 60
_MAX_FAILURES = 10
_failures: dict[str, deque] = defaultdict(deque)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_throttle(key: str) -> None:
    attempts = _failures[key]
    cutoff = monotonic() - _FAILURE_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if len(attempts) >= _MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")


@router.post("/auth/cashier-login")
def cashier_login(login: CashierLogin, request: Request, db: Session = Depends(get_db)):
    key = _client_key(request)
    _check_throttle(key)
    cashier = db.query(User).filter(User.username == login.cashier_id, User.role == UserRole.CASHIER.value).first()
    if cashier is None:
        _failures[key].append(monotonic())
        raise HTTPException(status_code=401, detail="Invalid counter ID")
    session_id = str(uuid4())
    db.add(AuthSession(session_id=session_id, user_id=cashier.user_id))
    token = create_access_token(user_id=cashier.user_id, username=cashier.username, role=cashier.role, session_id=session_id)
    db.commit()
    return {"access_token": token, "token_type": "bearer"}


@router.get("/cashiers")
def list_cashiers(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("manage_cashiers"))):
    rows = db.query(User).filter(
        User.role == UserRole.CASHIER.value,
        User.warehouse_id == current_user.get("warehouse_id"),
    ).order_by(User.full_name.asc()).all()
    sale_counts = {
        worker_id: count
        for worker_id, count in db.query(CounterSale.worker_id, func.count(CounterSale.sale_id)).filter(
            CounterSale.worker_id.in_([row.user_id for row in rows] or [0])
        ).group_by(CounterSale.worker_id).all()
    }
    return {"cashiers": [
        {"user_id": row.user_id, "full_name": row.full_name, "cashier_id": row.username, "sales_count": int(sale_counts.get(row.user_id, 0))}
        for row in rows
    ]}


@router.post("/cashiers")
def create_cashier(
    body: CashierCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_cashiers")),
):
    cashier_id = body.cashier_id
    if cashier_id is None:
        for _ in range(20):
            candidate = str(1 + randbelow(9)) + "".join(str(randbelow(10)) for _ in range(9))
            if db.query(User.user_id).filter(User.username == candidate).first() is None:
                cashier_id = candidate
                break
        if cashier_id is None:
            raise HTTPException(status_code=503, detail="Could not generate a unique counter ID; try again")
    elif db.query(User.user_id).filter(User.username == cashier_id).first() is not None:
        raise HTTPException(status_code=409, detail="This counter ID is already in use")
    cashier = User(
        username=cashier_id,
        full_name=body.full_name.strip(),
        email=None,
        role=UserRole.CASHIER.value,
        password_hash=hash_password(token_urlsafe(32)),
        warehouse_id=current_user.get("warehouse_id"),
    )
    db.add(cashier)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This counter ID is already in use")
    log_activity(db, current_user["user_id"], current_user["username"], "CASHIER_CREATED", f"Created counter account for {cashier.full_name}.")
    db.commit()
    return {"user_id": cashier.user_id, "full_name": cashier.full_name, "cashier_id": cashier.username}


@router.delete("/cashiers/{user_id}")
def delete_cashier(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_cashiers")),
):
    cashier = db.query(User).filter(User.user_id == user_id, User.role == UserRole.CASHIER.value).first()
    if cashier is None or cashier.warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=404, detail="Counter account not found")
    return remove_user(user_id, None, db, current_user)
