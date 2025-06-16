import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const AuthCallback = () => {
  const navigate = useNavigate();
  const { user, setUser } = useAuth();
  const [processed, setProcessed] = useState(false);

  useEffect(() => {
    if (processed) return; // Prevent double processing

    // Check for OAuth callback parameters
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    const username = urlParams.get('user');
    const role = urlParams.get('role');
    const uuid = urlParams.get('uuid');
    const error = urlParams.get('error');

    console.log('AuthCallback - URL params:', { token: !!token, username, role, uuid, error });
    console.log('AuthCallback - Current URL:', window.location.href);

    if (error) {
      console.error('OAuth error:', error);
      setProcessed(true);
      
      // Handle different error types
      let redirectUrl = '/login?error=' + encodeURIComponent(error);
      
      // Add email parameter if it exists for banned users
      if (error === 'user_banned') {
        const email = urlParams.get('email');
        if (email) {
          redirectUrl += '&email=' + encodeURIComponent(email);
        }
      }
      
      navigate(redirectUrl);
      return;
    }

    if (token && username && role && uuid) {
      // Successfully authenticated via OAuth callback
      const userInfo = { 
        username, 
        uuid, 
        role, 
        accessToken: token
      };
      
      console.log('AuthCallback - Setting user info:', userInfo);
      
      localStorage.setItem('user', JSON.stringify(userInfo));
      localStorage.setItem('token', token);
      
      // Update AuthContext state
      if (setUser) {
        setUser(userInfo);
      }
      
      console.log('AuthCallback - Navigating to:', (role === 'admin' || role === 'manager') ? '/dashboard' : '/search');
      
      setProcessed(true);
      
      // Navigate based on role with a small delay to ensure state is updated
      setTimeout(() => {
        if (role === 'admin' || role === 'manager') {
          navigate('/dashboard', { replace: true });
        } else {
          navigate('/search', { replace: true });
        }
      }, 100);
      
      return;
    } 
    
    if (user && !token) {
      // User is already logged in, navigate based on role
      console.log('AuthCallback - User already logged in:', user);
      setProcessed(true);
      if (user.role === 'admin' || user.role === 'manager') {
        navigate('/dashboard', { replace: true });
      } else {
        navigate('/search', { replace: true });
      }
      return;
    }
    
    // If no params and no user, wait a bit then redirect to login
    if (!token && !user) {
      console.log('AuthCallback - No auth data found, waiting...');
      setTimeout(() => {
        if (!processed) {
          console.log('AuthCallback - Timeout, redirecting to login');
          setProcessed(true);
          navigate('/login', { replace: true });
        }
      }, 2000); // Wait 2 seconds
    }
  }, [navigate, user, setUser, processed]);

  return (
    <div style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      minHeight: '100vh',
      backgroundColor: '#1a1a2e'
    }}>
      <div style={{ textAlign: 'center', color: 'white' }}>
        <div style={{ marginBottom: '1rem' }}>
          <div style={{
            width: '40px',
            height: '40px',
            border: '3px solid rgba(255,255,255,0.3)',
            borderTop: '3px solid white',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto'
          }}></div>
        </div>
        <p>Đang xử lý đăng nhập...</p>
        <p style={{ fontSize: '12px', opacity: 0.7, marginTop: '1rem' }}>
          Nếu trang này không tự động chuyển hướng, <a href="/login" style={{ color: '#4F46E5' }}>nhấn vào đây</a>
        </p>
      </div>
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default AuthCallback; 