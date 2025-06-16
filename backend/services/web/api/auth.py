from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import httpx
import secrets
import urllib.parse

from backend.core.config import settings
from backend.db.metadata import get_metadata_db

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory store for OAuth state (in production, use Redis)
oauth_states = {}

# Models
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user_info: dict

class GoogleLoginRequest(BaseModel):
    access_token: str

class UserInfo(BaseModel):
    username: str
    uuid: str
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
            
        # Get additional user info from database to ensure we have the latest data
        db = get_metadata_db()
        result = db.conn.execute("SELECT uuid, username, role FROM users WHERE username = ?", (username,))
        user = result.fetchone()
        
        if not user:
            raise credentials_exception
            
        return {
            "username": user["username"], 
            "role": user["role"], 
            "uuid": user["uuid"]
        }
    except JWTError:
        raise credentials_exception

async def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Check if user is an admin"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

async def get_admin_or_manager_user(current_user: dict = Depends(get_current_user)):
    """Check if user is an admin or manager"""
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or manager access required"
        )
    return current_user

async def verify_google_token(access_token: str) -> Optional[dict]:
    """Verify Google access token and get user info"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.googleapis.com/oauth2/v2/userinfo?access_token={access_token}"
            )
            
            if response.status_code == 200:
                user_info = response.json()
                return {
                    "email": user_info.get("email"),
                    "name": user_info.get("name"),
                    "verified_email": user_info.get("verified_email", False)
                }
            return None
    except Exception as e:
        print(f"Error verifying Google token: {e}")
        return None

# Endpoints
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Traditional username/password authentication
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
        "role": user_data["role"],
        "uuid": user_data["uuid"]
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
            "uuid": user_data["uuid"],
            "role": user_data["role"]
        }
    }

@router.get("/google")
async def google_login_redirect():
    """
    Redirect to Google OAuth authorization page
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Missing GOOGLE_CLIENT_ID."
        )
    
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {"timestamp": datetime.utcnow()}
    
    # Google OAuth 2.0 authorization URL
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": f"{settings.API_BASE_URL}/api/auth/google/callback",
        "response_type": "code",
        "scope": "email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }
    
    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url)

@router.get("/google/callback")
async def google_callback(code: str, state: str, error: Optional[str] = None):
    """
    Handle Google OAuth callback
    """
    if error:
        # Redirect to frontend with error
        frontend_url = f"{settings.FRONTEND_URL}/login?error={urllib.parse.quote(error)}"
        return RedirectResponse(url=frontend_url)
    
    # Verify state parameter
    if state not in oauth_states:
        frontend_url = f"{settings.FRONTEND_URL}/login?error=invalid_state"
        return RedirectResponse(url=frontend_url)
    
    # Clean up state
    del oauth_states[state]
    
    try:
        # Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": f"{settings.API_BASE_URL}/api/auth/google/callback",
                }
            )
            
            if token_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
            
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                raise HTTPException(status_code=400, detail="No access token received")
        
        # Get user info from Google
        google_user_info = await verify_google_token(access_token)
        
        if not google_user_info or not google_user_info.get("verified_email"):
            frontend_url = f"{settings.FRONTEND_URL}/login?error=unverified_email"
            return RedirectResponse(url=frontend_url)
        
        email = google_user_info["email"]
        
        # Create or get user
        db = get_metadata_db()
        try:
            user_data = db.create_or_get_google_user(email)
        except Exception as e:
            error_msg = str(e)
            if "is banned" in error_msg:
                frontend_url = f"{settings.FRONTEND_URL}/login?error=user_banned&email={urllib.parse.quote(email)}"
                return RedirectResponse(url=frontend_url)
            else:
                print(f"Database error: {e}")
                frontend_url = f"{settings.FRONTEND_URL}/login?error=database_error"
                return RedirectResponse(url=frontend_url)
        
        # Create JWT token
        token_data = {
            "sub": user_data["username"],
            "role": user_data["role"],
            "uuid": user_data["uuid"]
        }
        
        jwt_token, expires = create_access_token(token_data)
        expires_in = int((expires - datetime.utcnow()).total_seconds())
        
        # Redirect to frontend with token
        frontend_url = f"{settings.FRONTEND_URL}/auth/callback?token={jwt_token}&user={urllib.parse.quote(user_data['username'])}&role={user_data['role']}&uuid={user_data['uuid']}"
        return RedirectResponse(url=frontend_url)
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        frontend_url = f"{settings.FRONTEND_URL}/login?error=oauth_failed"
        return RedirectResponse(url=frontend_url)

@router.post("/google", response_model=Token)
async def google_login_token(google_request: GoogleLoginRequest):
    """
    Google OAuth authentication via token (legacy endpoint, kept for compatibility)
    """
    # Verify Google token
    google_user_info = await verify_google_token(google_request.access_token)
    
    if not google_user_info or not google_user_info.get("verified_email"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unverified Google token"
        )
    
    email = google_user_info["email"]
    
    # Create or get user
    db = get_metadata_db()
    user_data = db.create_or_get_google_user(email)
    
    # Create token data
    token_data = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "uuid": user_data["uuid"]
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
            "uuid": user_data["uuid"],
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
        uuid=current_user["uuid"],
        role=current_user["role"]
    )

@router.post("/refresh")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """
    Refresh access token
    """
    token_data = {
        "sub": current_user["username"],
        "role": current_user["role"],
        "uuid": current_user["uuid"]
    }
    
    access_token, expires = create_access_token(token_data)
    expires_in = int((expires - datetime.utcnow()).total_seconds())
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in
    } 