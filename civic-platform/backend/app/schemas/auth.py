"""Auth request/response schemas."""
from pydantic import BaseModel, EmailStr, Field, field_validator
import re

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)

class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=150)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=15)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

class RefreshRequest(BaseModel):
    refresh_token: str

class OtpVerifyRequest(BaseModel):
    identifier: str
    otp: str = Field(min_length=6, max_length=6)
    purpose: str = "verify"

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
