import { useState, useEffect, useContext, createContext } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is logged in on initial load from local storage
    const checkLoggedIn = () => {
      const storedUser = localStorage.getItem('user');
      const storedToken = localStorage.getItem('token');
      
      if (storedUser && storedToken) {
        setUser(JSON.parse(storedUser));
      }
      setLoading(false);
    };

    checkLoggedIn();
  }, []);

  // Traditional username/password login
  const login = async (username, password) => {
    setLoading(true);
    
    try {
      // Use FormData for traditional OAuth2 password flow
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);

      const response = await fetch(`${API_BASE_URL}/api/auth/token`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Login failed');
      }

      const data = await response.json();
      
      const userInfo = {
        username: data.user_info.username,
        uuid: data.user_info.uuid,
        role: data.user_info.role,
        accessToken: data.access_token
      };
      
      // Save user to local storage
      localStorage.setItem('user', JSON.stringify(userInfo));
      localStorage.setItem('token', data.access_token);
      setUser(userInfo);
      return true;
    } catch (error) {
      console.error('Login error:', error);
      return false;
    } finally {
      setLoading(false);
    }
  };

  // Google login function - redirect to backend
  const loginWithGoogle = async () => {
    try {
      setLoading(true);
      // Redirect to backend Google OAuth endpoint
      window.location.href = `${API_BASE_URL}/api/auth/google`;
      return true;
    } catch (error) {
      console.error('Google login error:', error);
      setLoading(false);
      return false;
    }
  };

  // Logout function
  const logout = async () => {
    try {
      localStorage.removeItem('user');
      localStorage.removeItem('token');
      setUser(null);
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: !!user,
        user,
        loading,
        login,
        loginWithGoogle,
        logout,
        setUser,
        isAdmin: user?.role === 'admin',
        isManager: user?.role === 'manager',
        isAdminOrManager: user?.role === 'admin' || user?.role === 'manager',
        userRole: user?.role || null
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  return useContext(AuthContext);
}; 