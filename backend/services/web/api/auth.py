from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from backend.core.config import settings
from backend.db.metadata import get_metadata_db

router = APIRouter(prefix="/auth", tags=["auth"])

# Models
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user_info: dict

class UserInfo(BaseModel):
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

# JWT functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.AUTH_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.AUTH_SECRET_KEY, algorithm="HS256")
    return encoded_jwt, expire

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate and decode JWT token to get current user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.AUTH_SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    db = get_metadata_db()
    # This is a simple version that doesn't hit the database again
    # In a more complex scenario, you would validate the user exists in the database
    
    return {"username": username, "role": payload.get("role", "user")}

async def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Check if user is an admin"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

# Endpoints
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and provide JWT token
    """
    db = get_metadata_db()
    authenticated, user_data = db.verify_user(form_data.username, form_data.password)
    
    if not authenticated or not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create token data
    token_data = {
        "sub": user_data["username"],
        "role": user_data["role"]
    }
    
    # Create access token
    access_token, expires = create_access_token(token_data)
    
    # Calculate expires_in in seconds
    expires_in = int((expires - datetime.utcnow()).total_seconds())
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user_info": {
            "username": user_data["username"],
            "full_name": user_data.get("full_name"),
            "email": user_data.get("email"),
            "role": user_data["role"]
        }
    }

@router.get("/me", response_model=UserInfo)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user info
    """
    return UserInfo(
        username=current_user["username"],
        role=current_user["role"]
    )

@router.post("/refresh")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """
    Refresh access token
    """
    token_data = {
        "sub": current_user["username"],
        "role": current_user["role"]
    }
    
    access_token, expires = create_access_token(token_data)
    expires_in = int((expires - datetime.utcnow()).total_seconds())
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in
    } 