from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.auth.permissions import has_permission
from app.auth.roles import UserRole
from app.auth.security import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from sqlalchemy.orm import Session


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")
        username = payload.get("username")
        role = payload.get("role")
        session_id = payload.get("sid")

        if user_id is None or username is None or role is None or session_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )

        active_session = db.query(AuthSession).filter(
            AuthSession.session_id == session_id,
            AuthSession.user_id == int(user_id),
        ).first()

        if active_session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This session is no longer active. Please sign in again",
            )

        user = db.query(User).filter(User.user_id == int(user_id)).first()
        if user is None or user.username != username or user.role != role:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is no longer active",
            )
        try:
            UserRole(role)
        except ValueError:
            raise HTTPException(status_code=403, detail="Unsupported account role")

        return {
            "user_id": int(user_id),
            "username": user.full_name,
            "email": user.email,
            "account_username": user.username,
            "role": role,
            "warehouse_id": user.warehouse_id,
            "session_id": session_id,
        }

    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token"
        )


def require_permission(permission: str):
    def permission_checker(
        current_user: dict = Depends(get_current_user)
    ):
        try:
            role = UserRole(current_user["role"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user role"
            )

        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )

        return current_user

    return permission_checker