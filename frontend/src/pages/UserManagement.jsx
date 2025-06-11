import { useState, useEffect } from 'react';
import { usersApi } from '../services/api';
import Pagination from '../components/Pagination';
import LoadingOverlay from '../components/LoadingOverlay';
import toast from 'react-hot-toast';
import '../styles/FilesList.css';

// Import Heroicons
import { 
  UsersIcon, 
  UserGroupIcon, 
  UserIcon,
  MagnifyingGlassIcon,
  ShieldCheckIcon,
  UserMinusIcon,
  NoSymbolIcon,
  CheckCircleIcon,
  CalendarIcon
} from '@heroicons/react/24/outline';

const ITEMS_PER_PAGE = 10;

// Helper function to format dates
const formatDate = (dateString) => {
  if (!dateString) return '';
  
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return dateString;
  
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear();
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  
  return `${day}/${month}/${year} ${hours}:${minutes}`;
};

// Helper function to convert date to YYYY-MM-DD for input elements
const toInputDateFormat = (dateString) => {
  if (!dateString) return '';
  
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
    return dateString;
  }
  
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateString)) {
    const [day, month, year] = dateString.split('/');
    return `${year}-${month}-${day}`;
  }
  
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '';
  
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  
  return `${year}-${month}-${day}`;
};

const UserManagement = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  
  // Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);
  
  // Action loading state
  const [actionLoading, setActionLoading] = useState({});
  const [loadingAction, setLoadingAction] = useState({ isLoading: false, message: '' });
  
  // Ban confirmation modal
  const [showBanConfirm, setShowBanConfirm] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [banAction, setBanAction] = useState('ban'); // 'ban' or 'unban'

  useEffect(() => {
    fetchUsers();
  }, [currentPage, searchTerm]);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      
      const response = await usersApi.getUsers(
        ITEMS_PER_PAGE,
        (currentPage - 1) * ITEMS_PER_PAGE,
        searchTerm
      );

      setUsers(response.users);
      setTotalUsers(response.total);
    } catch (error) {
      console.error('Error fetching users:', error);
      toast.error('Failed to fetch users');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    setSearchQuery(e.target.value);
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter') {
      setSearchTerm(searchQuery);
      setCurrentPage(1);
    }
  };

  const handleRoleUpdate = async (userId, newRole, username) => {
    const currentUser = JSON.parse(localStorage.getItem('user'));
    
    if (currentUser.id === userId && newRole !== 'admin') {
      toast.error('You cannot remove admin role from yourself');
      return;
    }

    try {
      setActionLoading(prev => ({ ...prev, [`role_${userId}`]: true }));
      
      await usersApi.updateUserRole(userId, newRole);
      
      toast.success(`User role updated to ${newRole}`);
      fetchUsers();
    } catch (error) {
      console.error('Error updating user role:', error);
      toast.error(error.response?.data?.detail || 'Failed to update user role');
    } finally {
      setActionLoading(prev => ({ ...prev, [`role_${userId}`]: false }));
    }
  };

  const handleBanUser = (user, action = 'ban') => {
    setSelectedUser(user);
    setBanAction(action);
    setShowBanConfirm(true);
  };

  const confirmBanAction = async () => {
    if (!selectedUser) return;
    
    const currentUser = JSON.parse(localStorage.getItem('user'));
    
    // Check if trying to ban/unban yourself
    if (currentUser.username === selectedUser.username) {
      toast.error('You cannot ban/unban yourself');
      return;
    }

    const actionMessage = banAction === 'ban' ? 'Banning user...' : 'Unbanning user...';
    setLoadingAction({ isLoading: true, message: actionMessage });

    try {
      if (banAction === 'ban') {
        await usersApi.banUser(selectedUser.id);
        toast.success(`User "${selectedUser.username}" banned successfully`);
      } else {
        await usersApi.unbanUser(selectedUser.id);
        toast.success(`User "${selectedUser.username}" unbanned successfully`);
      }
      
      fetchUsers();
    } catch (error) {
      console.error(`Error ${banAction}ning user:`, error);
      toast.error(error.response?.data?.detail || `Failed to ${banAction} user`);
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
      setShowBanConfirm(false);
      setSelectedUser(null);
    }
  };

  const handlePageChange = (page) => {
    setCurrentPage(page);
  };

  const clearSearch = () => {
    setSearchQuery('');
    setSearchTerm('');
    setCurrentPage(1);
    toast.success('Search cleared');
  };

  const totalPages = Math.ceil(totalUsers / ITEMS_PER_PAGE);

  if (loading && currentPage === 1) {
    return (
      <div className="users-page-container">
        <LoadingOverlay 
          isVisible={true}
          message="Loading users..."
        />
      </div>
    );
  }

  return (
    <div className="page-container files-list user-management">
      {/* Loading overlay */}
      <LoadingOverlay 
        isVisible={loadingAction.isLoading}
        message={loadingAction.message}
      />
      
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1>User Management</h1>
          <p>Manage system users and their permissions</p>
        </div>
        <div className="header-actions" style={{ 
          display: "flex", 
          alignItems: "center", 
          gap: "10px",
          height: "40px" // Fixed container height
        }}>
          <div className="search-box" style={{ 
            width: "360px",
            position: "relative",
            height: "40px", // Exact same height as button
            margin: 0,
            padding: 0,
            boxSizing: "border-box"
          }}>
            <div style={{ 
              position: "absolute",
              left: "10px",
              top: "50%",
              transform: "translateY(-50%)",
              zIndex: 2,
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}>
              <MagnifyingGlassIcon className="search-icon" style={{ width: "20px", height: "20px" }} />
            </div>
            <input 
              type="text" 
              placeholder="Search by username..." 
              value={searchQuery}
              onChange={handleSearch}
              onKeyDown={handleSearchKeyDown}
              style={{ 
                position: "absolute",
                left: 0,
                top: 0,
                width: "100%",
                height: "100%",
                paddingLeft: "40px", // Make room for the icon
                paddingRight: searchTerm ? "40px" : "10px", // Extra padding when clear button is visible
                margin: 0,
                boxSizing: "border-box",
                color: "#000000", /* Ensure text is visible */
                fontSize: "14px",
                fontWeight: "normal",
                background: "white",
                border: "none",
                outline: "none",
                zIndex: 1
              }}
            />
            {searchTerm && (
              <button 
                onClick={clearSearch}
                style={{
                  position: "absolute",
                  right: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  zIndex: 2,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#64748b",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "24px",
                  height: "24px",
                  padding: 0
                }}
                title="Clear search"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" style={{width: "16px", height: "16px"}}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Actions Bar */}
      <div className="documents-actions">
        <div className="documents-tabs">
          <button className="tab-btn active">
            <UsersIcon className="w-4 h-4" />
            All Users
            <span className="badge">{totalUsers}</span>
          </button>
        </div>
      </div>

      {/* Data Table */}
      <div className="card data-card">
        <div className="table-container">
          {loading ? (
            <div className="empty-state">
              <div className="loading-spinner">
                <svg className="w-8 h-8 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
              <p>Loading users...</p>
            </div>
          ) : users.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"></div>
              <h3>No users found</h3>
              {searchTerm ? (
                <p>No users match your search. Try using different keywords.</p>
              ) : (
                <p>No users available</p>
              )}
            </div>
          ) : (
            <table className="documents-table">
              <thead>
                <tr>
                  <th width="30%" className="text-center">User</th>
                  <th width="15%" className="text-center">Role</th>
                  <th width="15%" className="text-center">Created</th>
                  <th width="15%" className="text-center">Last Updated</th>
                  <th width="15%" className="text-center">Updated By</th>
                  <th width="10%" className="text-center">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="text-center">
                      <span className="document-title">{user.username}</span>
                    </td>
                    <td className="text-center">
                      <div className="flex justify-center">
                        <span className={`status-badge ${user.role === 'admin' ? 'admin' : 'user'}`}>
                          {user.role}
                        </span>
                        {(user.is_banned === 1 || user.is_banned === true) && (
                          <span className="status-badge banned" style={{marginLeft: '8px'}}>
                            BANNED
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-center">{formatDate(user.created_at)}</td>
                    <td className="text-center">{user.updated_at ? formatDate(user.updated_at) : '-'}</td>
                    <td className="text-center">{user.updated_by || '-'}</td>
                    <td>
                      <div className="action-buttons">
                        {(() => {
                          const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
                          const isCurrentUser = user.username === currentUser.username;
                          const isDefaultAdmin = user.username === 'admin'; // Default admin
                          const currentUserIsDefaultAdmin = currentUser.username === 'admin';
                          const isBanned = user.is_banned === 1 || user.is_banned === true;
                          
                          return (
                            <>
                              {/* Grant Admin Button */}
                              {user.role !== 'admin' && !isCurrentUser && !isBanned && (
                                <button
                                  className="action-icon process-btn"
                                  onClick={() => handleRoleUpdate(user.id, 'admin', user.username)}
                                  disabled={actionLoading[`role_${user.id}`]}
                                  title="Grant Admin"
                                >
                                  {actionLoading[`role_${user.id}`] ? (
                                    <div className="loading-spinner small" />
                                  ) : (
                                    <ShieldCheckIcon className="w-4 h-4" />
                                  )}
                                </button>
                              )}
                              
                              {/* Revoke Admin Button */}
                              {user.role === 'admin' && !isCurrentUser && !isDefaultAdmin && !isBanned && (
                                <button
                                  className="action-icon view-btn"
                                  onClick={() => handleRoleUpdate(user.id, 'user', user.username)}
                                  disabled={actionLoading[`role_${user.id}`]}
                                  title="Revoke Admin"
                                >
                                  {actionLoading[`role_${user.id}`] ? (
                                    <div className="loading-spinner small" />
                                  ) : (
                                    <UserMinusIcon className="w-4 h-4" />
                                  )}
                                </button>
                              )}
                              
                              {/* Unban Button */}
                              {isBanned && !isCurrentUser && (
                                <button
                                  className="action-icon process-btn"
                                  onClick={() => handleBanUser(user, 'unban')}
                                  disabled={actionLoading[`ban_${user.id}`]}
                                  title="Unban User"
                                >
                                  {actionLoading[`ban_${user.id}`] ? (
                                    <div className="loading-spinner small" />
                                  ) : (
                                    <CheckCircleIcon className="w-4 h-4" />
                                  )}
                                </button>
                              )}
                              
                              {/* Ban Button */}
                              {!isBanned && !isCurrentUser && !isDefaultAdmin && (
                                <>
                                  {/* Only default admin can ban other admins */}
                                  {(user.role !== 'admin' || currentUserIsDefaultAdmin) && (
                                    <button
                                      className="action-icon delete-btn"
                                      onClick={() => handleBanUser(user, 'ban')}
                                      disabled={actionLoading[`ban_${user.id}`]}
                                      title="Ban User"
                                    >
                                      {actionLoading[`ban_${user.id}`] ? (
                                        <div className="loading-spinner small" />
                                      ) : (
                                        <NoSymbolIcon className="w-4 h-4" />
                                      )}
                                    </button>
                                  )}
                                </>
                              )}
                            </>
                          );
                        })()}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {users.length > 0 && (
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={handlePageChange}
          />
        )}
      </div>

      {/* Ban/Unban Confirmation Modal */}
      {showBanConfirm && selectedUser && (
        <div className="modal-overlay" onClick={() => setShowBanConfirm(false)}>
          <div className="modal-content confirm-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{banAction === 'ban' ? 'Ban User' : 'Unban User'}</h2>
              <button className="close-btn" onClick={() => setShowBanConfirm(false)}>×</button>
            </div>
            <div className="modal-body">
              <p>
                Are you sure you want to {banAction} user "{selectedUser.username}"?
                {banAction === 'ban' && ' This will prevent them from accessing the system.'}
                {banAction === 'unban' && ' This will restore their access to the system.'}
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowBanConfirm(false)}>Cancel</button>
              <button 
                className={banAction === 'ban' ? 'btn-danger' : 'btn-primary'} 
                onClick={confirmBanAction}
              >
                {banAction === 'ban' ? 'Ban' : 'Unban'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserManagement;