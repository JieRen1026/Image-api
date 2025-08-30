from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel
import os

# simple in-memory user store for demo/marking
# username -> { "username": str, "password_hash": str, "role": "user"|"admin" }
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_users = {
    "alice": {"username": "alice", "password_hash": _pwd.hash("password1"), "role": "user"},
    "admin": {"username": "admin", "password_hash": _pwd.hash("admin123"), "role": "admin"},
}

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
router = APIRouter(prefix="/auth", tags=["auth"])

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class User(BaseModel):
    username: str
    role: str

def _authenticate(username: str, password: str) -> Optional[User]:
    u = _users.get(username)
    if not u or not _pwd.verify(password, u["password_hash"]):
        return None
    return User(username=u["username"], role=u["role"])

def _create_token(user: User, minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = _authenticate(form.username, form.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = _create_token(user)
    return Token(access_token=token)

def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username or not role:
            raise JWTError("missing claims")
        u = _users.get(username)
        if not u:
            raise JWTError("user not found")
        return User(username=username, role=role)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

def require_role(required: str):
    def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role != required:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user
    return checker

def verify_token(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user

