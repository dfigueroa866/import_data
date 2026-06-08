# src/data_staging/schemas/auth.py
"""Authentication related Pydantic schemas."""

from typing import Optional
from pydantic import BaseModel

class TokenUser(BaseModel):
    id: str
    email: str
    role: str
    organization_id: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    organization_id: str
    organization_name: Optional[str] = None

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class RefreshRequest(BaseModel):
    refresh_token: str

class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
