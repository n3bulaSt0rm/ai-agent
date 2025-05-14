from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel

from backend.core.config import settings
from backend.db.metadata import get_metadata_db

# Models
class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.AUTH_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.AUTH_SECRET_KEY, algorithm="HS256")
    return encoded_jwt

async def verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode a JWT token"""
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
        
        return {
            "username": username,
            "role": payload.get("role", "user")
        }
    except JWTError:
        raise credentials_exception

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Get the current authenticated user from token"""
    user_data = await verify_token(token)
    return user_data

async def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Check if the current user is an admin"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user 