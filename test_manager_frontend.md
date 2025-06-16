# Frontend Testing Plan for Manager Role

## 1. Navigation & Authentication

### Login & Navigation
- [ ] Manager login redirects to `/dashboard` instead of `/search`
- [ ] Google OAuth login with manager role redirects correctly  
- [ ] Logo clicks navigate to dashboard for manager users
- [ ] Manager sees same navbar items as admin (Dashboard, Users, AI Search, Documents)

### Route Protection
- [ ] Manager can access `/dashboard`
- [ ] Manager can access `/documents` (file list)
- [ ] Manager can access `/files/:id` (file detail)
- [ ] Manager can access `/users` (user management)
- [ ] Manager can access `/search` (AI search)
- [ ] Regular users cannot access admin/manager routes

## 2. User Management Features

### Role Permissions
- [ ] Only admin can see "Grant Manager" button for regular users
- [ ] Only admin can see "Grant Admin" button 
- [ ] Only admin can see "Revoke Role" button for managers/admins
- [ ] Manager can see ban/unban buttons for regular users
- [ ] Manager cannot see ban/unban buttons for other managers/admins
- [ ] Only admin can ban/unban managers or other admins

### UI Elements
- [ ] Manager role displays with blue badge styling
- [ ] Manager role badge shows "manager" text
- [ ] Action buttons appear/disappear based on current user role
- [ ] Loading states work correctly for role operations

## 3. File Management

### File Operations (Manager should have same access as admin)
- [ ] Manager can upload files
- [ ] Manager can view file list with all filters/search
- [ ] Manager can process files
- [ ] Manager can delete files (move to trash)
- [ ] Manager can restore files from trash
- [ ] Manager can update file metadata (description, keywords, date)
- [ ] Manager can view file statistics

## 4. Dashboard Access

### Dashboard Components  
- [ ] Manager sees file statistics (total, processing, processed)
- [ ] Manager sees storage usage information
- [ ] Manager sees system health status
- [ ] Manager sees recent documents lists
- [ ] Manager can upload files from dashboard modal

## 5. Error Scenarios

### Edge Cases
- [ ] Manager cannot perform admin-only actions
- [ ] Error messages display correctly for forbidden actions
- [ ] Manager role persists across browser refresh
- [ ] Manager role works correctly after token refresh

## 6. User Experience

### Visual Consistency
- [ ] Manager sees same UI as admin for shared features
- [ ] Manager role badge uses appropriate styling  
- [ ] Navigation highlights work correctly
- [ ] Permission-based UI changes are smooth

## Testing Checklist Instructions

1. **Create Test Users:**
   - Create a regular user account
   - Have admin grant manager role
   - Test login with manager credentials

2. **Navigation Testing:**
   - Login as manager and verify dashboard access
   - Click through all navigation items
   - Verify regular users cannot access manager routes

3. **User Management:**
   - Login as manager and go to Users page
   - Try to ban a regular user (should work)
   - Try to ban another manager (should not show button)
   - Login as admin and verify all role operations work

4. **File Management:**
   - Upload, process, delete files as manager
   - Compare UI with admin user to ensure consistency
   - Test all file operations and metadata updates

5. **Cross-Role Testing:**
   - Switch between admin, manager, and user accounts
   - Verify each role sees appropriate UI elements
   - Test permission boundaries are enforced

## Expected Results

- Manager has full access to all pages except role management restrictions
- Manager can ban/unban regular users but not other managers/admins  
- Only admin can grant/revoke manager roles
- UI correctly shows/hides elements based on user permissions
- All file and document management features work for managers
- Navigation and routing work seamlessly for manager role 