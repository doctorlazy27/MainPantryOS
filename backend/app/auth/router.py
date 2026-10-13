from datetime import datetime, timedelta
from secrets import randbelow
import os
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.roles import UserRole
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.models.registration_request import RegistrationRequest
from app.schemas.user import EmailOtpRequest, PasswordResetConfirm, UserLogin, UserRegister
from app.auth.dependencies import get_current_user, require_permission
from app.models.auth_session import AuthSession
from app.models.warehouse import Warehouse
from app.models.auth_otp import AuthOtp
from app.services.email import send_otp_email
from app.services.notification import notify_roles


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.get("/me")
def get_current_user_info(
    current_user: dict = Depends(get_current_user)
):
    return current_user


@router.get("/roles")
def get_roles():
    return {
        "roles": [UserRole.MANAGER.value, UserRole.WAREHOUSE_WORKER.value]
    }


@router.post("/logout")
def logout_user(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    db.query(AuthSession).filter(
        AuthSession.session_id == current_user["session_id"],
        AuthSession.user_id == current_user["user_id"],
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "Session revoked"}

@router.get("/warehouses")
def get_signup_warehouses(db: Session = Depends(get_db)):
    return {"warehouses": db.query(Warehouse).order_by(Warehouse.name.asc()).all()}


def _issue_otp(db: Session, email: str, purpose: str) -> str:
    code = f"{randbelow(1_000_000):06d}"
    db.query(AuthOtp).filter(AuthOtp.email == email, AuthOtp.purpose == purpose, AuthOtp.consumed_at.is_(None)).update({"consumed_at": datetime.utcnow()})
    db.add(AuthOtp(email=email, purpose=purpose, code_hash=hash_password(code), expires_at=datetime.utcnow() + timedelta(minutes=10)))
    db.commit()
    try:
        send_otp_email(email, code, purpose)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return code


def _consume_otp(db: Session, email: str, purpose: str, code: str) -> None:
    otp = db.query(AuthOtp).filter(AuthOtp.email == email, AuthOtp.purpose == purpose, AuthOtp.consumed_at.is_(None)).order_by(AuthOtp.otp_id.desc()).first()
    if otp is None or otp.expires_at < datetime.utcnow() or otp.attempts >= 5:
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    otp.attempts += 1
    if not verify_password(code, otp.code_hash):
        db.commit()
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    otp.consumed_at = datetime.utcnow()
    db.commit()


def _generate_internal_username(db: Session, email: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", email.split("@", 1)[0]) or "account"
    candidate = base[:90]
    suffix = 1
    while db.query(User).filter(User.username == candidate).first():
        suffix += 1
        candidate = f"{base[:90]}-{suffix}"
    return candidate


@router.post("/signup-otp")
def request_signup_otp(request: EmailOtpRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    if db.query(User).filter(User.email == email).first() or db.query(RegistrationRequest).filter(RegistrationRequest.email == email, RegistrationRequest.status != "rejected").first():
        raise HTTPException(status_code=409, detail="An account already uses this email address")
    code = _issue_otp(db, email, "signup")
    response = {"message": "Verification code sent"}
    if os.getenv("DEV_RETURN_OTP", "false").lower() == "true": response["dev_otp"] = code
    return response


@router.post("/register")
def register_user(
    user: UserRegister,
    db: Session = Depends(get_db)
):
    email = user.email.strip().lower()
    _consume_otp(db, email, "signup", user.otp)
    if user.role not in set(UserRole):
        raise HTTPException(status_code=400, detail="Only manager and warehouse worker accounts can be created")
    existing_user = db.query(User).filter(User.email == email).first()
    existing_request = db.query(RegistrationRequest).filter(
        RegistrationRequest.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email address already belongs to an active account",
        )

    if existing_request and existing_request.status != "rejected":
        raise HTTPException(
            status_code=409,
            detail=f"A registration request for this email is already {existing_request.status}",
        )

    warehouse = db.query(Warehouse).filter(Warehouse.warehouse_id == user.warehouse_id).first() if user.warehouse_id else None
    if warehouse is None and user.warehouse_name:
        warehouse = db.query(Warehouse).filter(Warehouse.name.ilike(user.warehouse_name.strip())).first()
    if warehouse is None and user.role == UserRole.MANAGER and user.warehouse_name:
        warehouse = Warehouse(
            name=user.warehouse_name.strip(),
            location=user.warehouse_name.strip(),
        )
        db.add(warehouse)
        db.flush()

        new_manager = User(
            username=_generate_internal_username(db, email),
            full_name=user.full_name,
            email=email,
            role=user.role.value,
            password_hash=hash_password(user.password),
            warehouse_id=warehouse.warehouse_id,
        )
        db.add(new_manager)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Email address already exists")
        db.refresh(new_manager)
        return {
            "message": "Warehouse created and manager account activated",
            "user_id": new_manager.user_id,
            "username": new_manager.username,
            "role": new_manager.role,
            "warehouse_id": new_manager.warehouse_id,
            "status": "approved",
        }
    if warehouse is None:
        if user.role == UserRole.MANAGER and not user.warehouse_id and not user.warehouse_name:
            raise HTTPException(status_code=400, detail="Enter a new warehouse name to create the first manager account")
        if user.role == UserRole.MANAGER and user.warehouse_id:
            raise HTTPException(
                status_code=400,
                detail="Warehouse ID does not exist. To create a new warehouse, enter its name instead of an ID.",
            )
        raise HTTPException(status_code=400, detail="Selected warehouse does not exist")

    if existing_request and existing_request.status == "rejected":
        existing_request.full_name = user.full_name
        existing_request.email = email
        existing_request.role = user.role.value
        existing_request.warehouse_id = warehouse.warehouse_id
        existing_request.password_hash = hash_password(user.password)
        existing_request.status = "pending"
        existing_request.requested_at = datetime.utcnow()
        existing_request.reviewed_at = None
        existing_request.reviewed_by = None
        notify_roles(db, {"manager"}, "Account approval needed", f"{existing_request.full_name} requested warehouse access with {email}.", "registration_request", warehouse.warehouse_id)
        db.commit()
        db.refresh(existing_request)
        return {
            "message": "Registration request submitted for manager approval",
            "request_id": existing_request.request_id,
            "username": existing_request.username,
            "full_name": existing_request.full_name,
            "role": existing_request.role,
            "status": existing_request.status
        }

    request = RegistrationRequest(
        username=_generate_internal_username(db, email),
        full_name=user.full_name,
        email=email,
        role=user.role.value,
            warehouse_id=warehouse.warehouse_id,
        password_hash=hash_password(user.password),
        status="pending"
    )

    db.add(request)
    try:
        db.flush()
        notify_roles(db, {"manager"}, "Account approval needed", f"{request.full_name} requested warehouse access with {email}.", "registration_request", warehouse.warehouse_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A registration request for this email already exists")
    db.refresh(request)

    return {
        "message": "Registration request submitted for manager approval",
        "request_id": request.request_id,
        "username": request.username,
        "full_name": request.full_name,
        "role": request.role,
            "warehouse_id": request.warehouse_id,
        "status": request.status
    }


@router.post("/password-reset/request")
def request_password_reset(request: EmailOtpRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    if db.query(User).filter(User.email == email).first() is None:
        return {"message": "If that email belongs to an account, a verification code was sent"}
    code = _issue_otp(db, email, "password_reset")
    response = {"message": "If that email belongs to an account, a verification code was sent"}
    if os.getenv("DEV_RETURN_OTP", "false").lower() == "true": response["dev_otp"] = code
    return response


@router.post("/password-reset/confirm")
def confirm_password_reset(request: PasswordResetConfirm, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    _consume_otp(db, email, "password_reset", request.otp)
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=400, detail="Account not found")
    user.password_hash = hash_password(request.new_password)
    db.query(AuthSession).filter(AuthSession.user_id == user.user_id).delete(synchronize_session=False)
    db.commit()
    return {"message": "Password updated. You can now sign in."}


@router.get("/registration-requests")
def get_registration_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users"))
):
    requests = db.query(RegistrationRequest).filter(
        RegistrationRequest.status == "pending",
        RegistrationRequest.warehouse_id == current_user.get("warehouse_id"),
    ).order_by(RegistrationRequest.requested_at.asc()).all()

    return {
        "requests": [
            {
                "request_id": request.request_id,
                "username": request.username,
                "full_name": request.full_name,
                "role": request.role,
                "warehouse_id": request.warehouse_id,
                "status": request.status,
                "requested_at": request.requested_at,
            }
            for request in requests
        ]
    }


@router.patch("/registration-requests/{request_id}/approve")
def approve_registration_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users"))
):
    request = db.query(RegistrationRequest).filter(
        RegistrationRequest.request_id == request_id,
        RegistrationRequest.status == "pending",
        RegistrationRequest.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if request is None:
        raise HTTPException(status_code=404, detail="Pending registration request not found")

    try:
        UserRole(request.role)
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail="This signup requested a retired role. Reject it and ask the applicant to submit a new request with a supported role.",
        ) from error

    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=request.username,
        full_name=request.full_name,
        email=request.email,
        role=request.role,
        password_hash=request.password_hash,
        warehouse_id=request.warehouse_id,
    )
    db.add(user)
    request.status = "approved"
    request.reviewed_at = datetime.utcnow()
    request.reviewed_by = current_user["user_id"]
    db.commit()

    return {
        "message": "Registration approved",
        "request_id": request.request_id,
        "username": user.username,
        "role": user.role,
            "warehouse_id": user.warehouse_id,
        "status": request.status,
    }


@router.patch("/registration-requests/{request_id}/reject")
def reject_registration_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users"))
):
    request = db.query(RegistrationRequest).filter(
        RegistrationRequest.request_id == request_id,
        RegistrationRequest.status == "pending",
        RegistrationRequest.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if request is None:
        raise HTTPException(status_code=404, detail="Pending registration request not found")

    request.status = "rejected"
    request.reviewed_at = datetime.utcnow()
    request.reviewed_by = current_user["user_id"]
    db.commit()

    return {
        "message": "Registration rejected",
        "request_id": request.request_id,
        "username": request.username,
        "status": request.status,
    }


@router.post("/login")
def login_user(
    user: UserLogin,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.email == user.email.strip().lower()
    ).first()

    if not existing_user:
        pending_request = db.query(RegistrationRequest).filter(
            RegistrationRequest.email == user.email.strip().lower(),
            RegistrationRequest.status == "pending",
        ).first()
        if pending_request:
            raise HTTPException(
                status_code=403,
                detail="This account is waiting for manager approval",
            )
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not verify_password(
        user.password,
        existing_user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    session_id = str(uuid4())
    db.add(AuthSession(session_id=session_id, user_id=existing_user.user_id))

    access_token = create_access_token(
        user_id=existing_user.user_id,
        username=existing_user.username,
        role=existing_user.role,
        session_id=session_id,
    )
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }