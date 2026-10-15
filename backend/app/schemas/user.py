from pydantic import BaseModel, Field

from app.auth.roles import UserRole


class UserRegister(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    otp: str = Field(min_length=6, max_length=6)
    role: UserRole
    warehouse_id: int | None = Field(default=None, gt=0)
    warehouse_name: str | None = Field(default=None, min_length=1, max_length=100)


class UserLogin(BaseModel):
    email: str
    password: str


class UserDelete(BaseModel):
    password: str = Field(default="", max_length=128)


class EmailOtpRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class PasswordResetConfirm(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)