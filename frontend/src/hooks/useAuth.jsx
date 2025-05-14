import { useState, useEffect, useContext, createContext } from 'react';

// Hardcoded credentials 
const ADMIN_USER = { 
  username: 'admin', 
  password: 'admin123',
  role: 'admin'
};

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is logged in on initial load from local storage
    const checkLoggedIn = () => {
      const storedUser = localStorage.getItem('user');
      if (storedUser) {
        setUser(JSON.parse(storedUser));
      }
      setLoading(false);
    };

    checkLoggedIn();
  }, []);

  // Simple login function with hardcoded credentials
  const login = async (username, password) => {
    setLoading(true);
    
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 500));
    
    try {
      // Check against hardcoded credentials
      if (username === ADMIN_USER.username && password === ADMIN_USER.password) {
        const userInfo = {
          username: ADMIN_USER.username,
          role: ADMIN_USER.role
        };
        
        // Save user to local storage
        localStorage.setItem('user', JSON.stringify(userInfo));
        setUser(userInfo);
        return true;
      }
      return false;
    } catch (error) {
      console.error('Login error:', error);
      return false;
    } finally {
      setLoading(false);
    }
  };

  // Logout function
  const logout = () => {
    localStorage.removeItem('user');
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: !!user,
        user,
        loading,
        login,
        logout
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  return useContext(AuthContext);
}; 