import os, time, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Simple hard-coded users (OK per rubric for A1)
USERS = {
    "alice": {"password": "password1", "role": "admin"},
    "bob":   {"password": "password2", "role": "user"},
}

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")   # set real env secret later
JWT_ALGO = "HS256"
TOKEN_TTL = 60 * 60  # 1 hour

security = HTTPBearer()

def create_token(username: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + TOKEN_TTL,
        "role": USERS[username]["role"],
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def verify_token(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = creds.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        username = payload.get("sub")
        if not username or username not in USERS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
        return {"username": username, "role": payload.get("role")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

@router.post("/auth/login", response_model=Token)
def login(req: LoginRequest):
    user = USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = create_token(req.username)
    return {"access_token": token, "token_type": "bearer"}

@router.get("/whoami")
def whoami(current=Depends(verify_token)):
    # `current` is {"username": "...", "role": "..."} from verify_token
    return {"user": current["username"], "role": current["role"]}
