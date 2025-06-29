from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from backend.common.config import settings
from backend.adapter.sql.metadata import get_metadata_db
from backend.services.web.api.auth import get_admin_user, get_admin_or_manager_user

router = APIRouter(prefix="/users", tags=["users"])

class UserResponse(BaseModel):
    uuid: str
    username: str
    role: str
    created_at: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    is_banned: Optional[int] = None

class UserRoleUpdateRequest(BaseModel):
    role: str

class UsersListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    limit: int
    offset: int

@router.get("/", response_model=UsersListResponse)
async def list_users(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search by username"),
    sort_by: Optional[str] = Query(None, description="Field to sort by (username, role, created_at)"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc, desc)"),
    date: Optional[str] = Query(None, description="Filter by creation date (YYYY-MM-DD)"),
    current_user: dict = Depends(get_admin_or_manager_user)
):
    """
    Get list of users (admin only) with pagination, search, sorting and filtering
    """
    try:
        db = get_metadata_db()
        
        # Get users with pagination, search, sorting and filtering
        users = db.get_all_users_advanced(
            limit=limit, 
            offset=offset, 
            search_query=search,
            sort_by=sort_by,
            sort_order=sort_order,
            date_filter=date
        )
        total_count = db.get_users_count_advanced(search_query=search, date_filter=date)
        
        # Format users for response
        user_responses = []
        for user in users:
            user_responses.append(UserResponse(**user))
        
        return UsersListResponse(
            users=user_responses,
            total=total_count,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get users: {str(e)}")

@router.get("/{user_uuid}", response_model=UserResponse)
async def get_user(
    user_uuid: str,
    current_user: dict = Depends(get_admin_or_manager_user)
):
    """
    Get specific user by ID (admin only)
    """
    try:
        db = get_metadata_db()
        user = db.get_user_by_uuid(user_uuid)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserResponse(**user)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")

@router.put("/{user_uuid}/role")
async def update_user_role(
    user_uuid: str,
    role_update: UserRoleUpdateRequest,
    current_user: dict = Depends(get_admin_user)  # Only admin can change roles
):
    """
    Update user role (admin only with restrictions)
    - Cannot change your own role
    - Cannot change default admin role
    - Only admin can grant/revoke manager roles
    - Manager can only be granted/revoked by admin
    """
    try:
        if role_update.role not in ['admin', 'manager', 'user']:
            raise HTTPException(status_code=400, detail="Role must be 'admin', 'manager', or 'user'")
        
        db = get_metadata_db()
        
        # Check if user exists
        user = db.get_user_by_uuid(user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prevent self-role change
        if user_uuid == current_user.get('uuid'):
            raise HTTPException(status_code=400, detail="Cannot change your own role")
        
        # Prevent changing default admin role
        if user['username'] == settings.ADMIN_USERNAME:
            raise HTTPException(status_code=400, detail="Cannot change default admin role")
        
        # Prevent granting admin role through API
        if role_update.role == 'admin':
            raise HTTPException(status_code=403, detail="Cannot grant admin role through this interface")
        
        # Only admin can grant or revoke manager role
        # Admin role can only be created through direct database access or system configuration
        
        # Update role
        success = db.update_user_role(
            user_uuid=user_uuid,
            new_role=role_update.role,
            updated_by=current_user['username']
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update user role")
        
        # Get updated user
        updated_user = db.get_user_by_uuid(user_uuid)
        
        return {
            "message": f"User role updated to {role_update.role}",
            "user": UserResponse(**updated_user)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user role: {str(e)}")

@router.post("/{user_uuid}/ban")
async def ban_user(
    user_uuid: str,
    current_user: dict = Depends(get_admin_or_manager_user)
):
    """
    Ban user (admin and manager with restrictions)
    - Only admin can ban manager or other admin users  
    - Manager can only ban regular users
    - Cannot ban yourself
    """
    try:
        db = get_metadata_db()
        
        # Check if user exists
        user = db.get_user_by_uuid(user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prevent self-banning
        if user['username'] == current_user['username']:
            raise HTTPException(status_code=400, detail="Cannot ban yourself")
        
        # Prevent banning default admin
        if user['username'] == settings.ADMIN_USERNAME:
            raise HTTPException(status_code=400, detail="Cannot ban default admin user")
        
        # Permission check: Only admin can ban managers or other admins
        if user['role'] in ['admin', 'manager'] and current_user['role'] != 'admin':
            raise HTTPException(status_code=403, detail="Only admin can ban manager or admin users")
        
        # Check if user is already banned
        is_banned = user.get('is_banned', 0)
        if is_banned == 1 or is_banned is True:
            raise HTTPException(status_code=400, detail="User is already banned")
        
        # Ban user
        success = db.ban_user(
            user_uuid=user_uuid,
            banned_by=current_user['username']
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to ban user")
        
        return {
            "message": f"User {user['username']} banned successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ban user: {str(e)}")

@router.post("/{user_uuid}/unban")
async def unban_user(
    user_uuid: str,
    current_user: dict = Depends(get_admin_or_manager_user)
):
    """
    Unban user (admin and manager with restrictions)
    - Only admin can unban manager or other admin users
    - Manager can only unban regular users
    """
    try:
        db = get_metadata_db()
        
        # Check if user exists
        user = db.get_user_by_uuid(user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Permission check: Only admin can unban managers or other admins
        if user['role'] in ['admin', 'manager'] and current_user['role'] != 'admin':
            raise HTTPException(status_code=403, detail="Only admin can unban manager or admin users")
        
        # Check if user is actually banned
        is_banned = user.get('is_banned', 0)
        if is_banned == 0 or is_banned is False or is_banned is None:
            raise HTTPException(status_code=400, detail="User is not banned")
        
        # Unban user
        success = db.unban_user(
            user_uuid=user_uuid,
            unbanned_by=current_user['username']
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to unban user")
        
        return {
            "message": f"User {user['username']} unbanned successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unban user: {str(e)}")

@router.get("/stats/summary")
async def get_user_stats(current_user: dict = Depends(get_admin_or_manager_user)):
    """
    Get user statistics (admin and manager)
    """
    try:
        db = get_metadata_db()
        
        # Get total users
        total_users = db.get_users_count()
        
        # Get admin count
        result = db.conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = result.fetchone()[0]
        
        # Get manager count
        result = db.conn.execute("SELECT COUNT(*) FROM users WHERE role = 'manager'")
        manager_count = result.fetchone()[0]
        
        # Get regular user count
        user_count = total_users - admin_count - manager_count
        
        # Get recent users (last 7 days)
        from datetime import datetime, timedelta
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        result = db.conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (week_ago,))
        recent_users = result.fetchone()[0]
        
        return {
            "total": total_users,
            "admin": admin_count,
            "manager": manager_count,
            "user": user_count,
            "recent": recent_users
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user stats: {str(e)}")

@router.get("/stats")
async def get_user_statistics(current_user: dict = Depends(get_admin_or_manager_user)):
    """
    Get detailed user statistics (admin and manager) - Similar format to files stats
    """
    try:
        db = get_metadata_db()
        
        # Get total users
        total_users = db.get_users_count()
        
        # Get users by role
        result = db.conn.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
        role_counts = {row[0]: row[1] for row in result.fetchall()}
        
        # Get recent activity (last 30 days)
        from datetime import datetime, timedelta
        month_ago = (datetime.now() - timedelta(days=30)).isoformat()
        result = db.conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (month_ago,))
        recent_month = result.fetchone()[0]
        
        # Get today's new users
        today = datetime.now().date().isoformat()
        result = db.conn.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?", (today,))
        today_new = result.fetchone()[0]
        
        return {
            "total": total_users,
            "admin": role_counts.get("admin", 0),
            "manager": role_counts.get("manager", 0),
            "user": role_counts.get("user", 0),
            "recent_month": recent_month,
            "today_new": today_new,
            "by_role": role_counts
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user statistics: {str(e)}") 