# Test Plan for Manager Role Implementation

## Backend Testing

### 1. Database and Authentication
- [ ] Verify `update_user_role` accepts 'manager' role
- [ ] Test `get_admin_or_manager_user` dependency allows manager access
- [ ] Test login with manager role returns correct permissions

### 2. Users API Testing  
- [ ] Manager can access `/users/` endpoint
- [ ] Manager can access `/users/{uuid}` endpoint  
- [ ] Only admin can grant/revoke manager role via `/users/{uuid}/role`
- [ ] Manager can ban/unban users but not managers/admins
- [ ] Only admin can ban/unban managers
- [ ] Manager can access user stats endpoints

### 3. Files API Testing
- [ ] Manager can upload files
- [ ] Manager can list/view files
- [ ] Manager can process files  
- [ ] Manager can delete/restore files
- [ ] Manager can update file metadata

## Frontend Testing

### 1. Authentication Flow
- [ ] Manager login redirects to dashboard (not search)
- [ ] Manager sees admin navbar options
- [ ] Manager can access all admin routes

### 2. User Management
- [ ] Manager role displays with blue badge
- [ ] Only admin sees "Grant Manager" button for users
- [ ] Only admin sees "Grant Admin" button for users/managers
- [ ] Only admin can revoke manager/admin roles
- [ ] Manager can ban/unban users only
- [ ] Only admin can ban/unban managers

### 3. Navigation & Routes
- [ ] Manager can access `/dashboard`
- [ ] Manager can access `/documents` 
- [ ] Manager can access `/files/:id`
- [ ] Manager can access `/users`
- [ ] Regular users cannot access admin routes

## Test Scenarios

### Scenario 1: Admin promotes user to manager
1. Admin logs in
2. Goes to Users page
3. Finds regular user
4. Clicks "Grant Manager" button
5. User role updates to manager
6. Manager can now access admin features

### Scenario 2: Manager tries to ban another manager (should fail)
1. Manager logs in
2. Goes to Users page  
3. Finds another manager
4. Ban button should not be visible OR action should fail

### Scenario 3: Only admin can demote manager
1. Admin logs in
2. Goes to Users page
3. Finds manager user
4. Clicks "Revoke Manager Role" button
5. User becomes regular user

### Expected Permissions Matrix

| Action | Admin | Manager | User |
|--------|-------|---------|------|
| View Dashboard | ✅ | ✅ | ❌ |
| Upload Files | ✅ | ✅ | ❌ |
| Manage Files | ✅ | ✅ | ❌ |
| View Users | ✅ | ✅ | ❌ |
| Grant Manager | ✅ | ❌ | ❌ |
| Grant Admin | ✅ | ❌ | ❌ |
| Revoke Manager/Admin | ✅ | ❌ | ❌ |
| Ban Users | ✅ | ✅ | ❌ |
| Ban Managers | ✅ | ❌ | ❌ |
| Ban Admins | ✅ | ❌ | ❌ |

## API Endpoints Updated

### Authentication
- `get_admin_or_manager_user()` - New dependency

### Users API
- `GET /users/` - Now accepts managers
- `GET /users/{uuid}` - Now accepts managers  
- `PUT /users/{uuid}/role` - Still admin-only
- `POST /users/{uuid}/ban` - Now accepts managers (with restrictions)
- `POST /users/{uuid}/unban` - Now accepts managers (with restrictions)
- `GET /users/stats` - Now accepts managers

### Files API  
- All endpoints now accept managers via `get_admin_or_manager_user`

## Frontend Components Updated

### Authentication
- `useAuth.jsx` - Added `isManager`, `isAdminOrManager` 
- `Login.jsx` - Manager redirects to dashboard
- `AuthCallback.jsx` - Manager redirects to dashboard
- `App.jsx` - AdminRoute → AdminOrManagerRoute

### User Management
- `UserManagement.jsx` - Complex button logic for manager permissions
- `UserManagement.css` - Blue badge style for manager

### API
- `api.js` - Updated user stats to include manager count 