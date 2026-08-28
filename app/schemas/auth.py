import re

from pydantic import BaseModel, EmailStr, field_validator

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")


class SignupRequest(BaseModel):
    username: str
    display_name: str
    email: EmailStr
    website_url: str = ""  # honeypot — real users never fill this in

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("Username must be 3-30 characters (letters, numbers, . _ -).")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class ForgotPasswordRequest(BaseModel):
    username: str


class ResetPasswordRequest(BaseModel):
    username: str
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class SetNewPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class MessageResponse(BaseModel):
    success: bool
    message: str | None = None
    error: str | None = None


class LoginResponse(BaseModel):
    success: bool
    display_name: str
    must_reset_password: bool
