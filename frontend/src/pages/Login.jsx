import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import '../styles/Login.css';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);
  const [error, setError] = useState('');
  const [fadeIn, setFadeIn] = useState(false);
  const [showBannedModal, setShowBannedModal] = useState(false);
  const [bannedEmail, setBannedEmail] = useState('');
  const { login, loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const loginPageRef = useRef(null);

  useEffect(() => {
    // Trigger fade-in animation after component mounts
    setTimeout(() => setFadeIn(true), 100);
    
    // Check for error from OAuth callback
    const urlParams = new URLSearchParams(window.location.search);
    const errorParam = urlParams.get('error');
    const email = urlParams.get('email');
    
    if (errorParam) {
      switch (errorParam) {
        case 'user_banned':
          setError(`Your account ${email || ''} has been banned. Please contact administrator for assistance.`);
          setBannedEmail(email);
          setShowBannedModal(true);
          break;
        case 'invalid_state':
          setError('Security error: Invalid authentication state. Please try again.');
          break;
        case 'unverified_email':
          setError('Your Google email is not verified. Please verify your email and try again.');
          break;
        case 'database_error':
          setError('Database error occurred. Please try again later.');
          break;
        case 'oauth_failed':
          setError('Google authentication failed. Please try again.');
          break;
        default:
          setError('Authentication error occurred. Please try again.');
      }
      
      // Clear URL parameters
      window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    // Create floating particles
    if (loginPageRef.current) {
      createParticles();
    }
  }, []);
  
  const createParticles = () => {
    const container = document.createElement('div');
    container.className = 'particles-container';
    
    // Create 50 particles with random properties
    for (let i = 0; i < 50; i++) {
      const particle = document.createElement('div');
      particle.className = 'particle';
      
      // Random horizontal position
      const leftPos = Math.random() * 100;
      particle.style.left = `${leftPos}%`;
      
      // Random size (1-4px)
      const size = 1 + Math.random() * 3;
      particle.style.width = `${size}px`;
      particle.style.height = `${size}px`;
      
      // Random opacity
      const opacity = 0.2 + Math.random() * 0.3;
      particle.style.backgroundColor = `rgba(255, 255, 255, ${opacity})`;
      
      // Random animation duration (8-15s)
      const duration = 8 + Math.random() * 7;
      particle.style.setProperty('--float-duration', `${duration}s`);
      
      // Random animation delay
      const delay = Math.random() * 5;
      particle.style.animationDelay = `${delay}s`;
      
      container.appendChild(particle);
    }
    
    // Add container to the login page
    if (loginPageRef.current) {
      loginPageRef.current.appendChild(container);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      const success = await login(username, password);
      
      if (success) {
        // Add a slight delay before redirect for better UX
        setTimeout(() => {
          // Check user role for navigation
          const storedUser = localStorage.getItem('user');
          if (storedUser) {
            const userData = JSON.parse(storedUser);
            if (userData.role === 'admin') {
              navigate('/dashboard');
            } else {
              navigate('/search'); // Navigate to intelligent search for regular users
            }
          } else {
            navigate('/dashboard'); // Fallback
          }
        }, 300);
      } else {
        setError('Invalid username or password');
      }
    } catch (error) {
      setError(error.message || 'An error occurred during login');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setIsGoogleLoading(true);
    setError('');

    try {
      const success = await loginWithGoogle();
      
      if (!success) {
        setError('Google login failed. Please try again.');
      }
      // Note: No need to redirect here as loginWithGoogle() redirects to backend
    } catch (error) {
      setError(error.message || 'An error occurred during Google login');
      setIsGoogleLoading(false);
    }
  };

  return (
    <div className="login-page" ref={loginPageRef}>
      <div className={`login-container ${fadeIn ? 'fade-in' : ''}`}>
        <div className="animated-background">
          <div className="shape shape1"></div>
          <div className="shape shape2"></div>
          <div className="shape shape3"></div>
        </div>
        
        <div className="login-card">
          <div className="card-header">
            <div className="logo-container">
              <div className="logo-icon">AI</div>
            </div>
            <h1 className="app-title">AIAgent</h1>
            <p className="app-subtitle">Document Management Platform</p>
          </div>

          {error && (
            <div className="error-message">
              <i className="error-icon"></i>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="username" className="field-label">Username</label>
              <div className="input-with-icon">
                <i className="input-icon user-icon"></i>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  required
                  className="normal-input"
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="password" className="field-label">Password</label>
              <div className="input-with-icon">
                <i className="input-icon password-icon"></i>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  className="normal-input"
                />
              </div>
            </div>

            <button
              type="submit"
              className="login-button"
              disabled={isLoading}
            >
              {isLoading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <div className="divider">
            <span>or</span>
          </div>

          <button
            type="button"
            className="google-login-button"
            onClick={handleGoogleLogin}
            disabled={isGoogleLoading}
          >
            <svg className="google-icon" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            {isGoogleLoading ? 'Connecting...' : 'Continue with Google'}
          </button>
        </div>
      </div>
      
      {(isLoading || isGoogleLoading) && (
        <div className="loading-overlay">
          <div className="loading-popup">
            <span className="spinner"></span>
            <span>{isLoading ? 'Signing in...' : 'Connecting with Google...'}</span>
          </div>
        </div>
      )}
      
      {/* Banned User Modal */}
      {showBannedModal && (
        <div className="modal-overlay-banned" onClick={() => setShowBannedModal(false)}>
          <div className="modal-content-banned" onClick={e => e.stopPropagation()}>
            <div className="modal-header-banned">
              <div className="banned-icon">🚫</div>
              <h2>Account Banned</h2>
              <button className="close-btn-banned" onClick={() => setShowBannedModal(false)}>×</button>
            </div>
            <div className="modal-body-banned">
              <p>Your account <strong>{bannedEmail}</strong> has been banned from this system.</p>
              <p>This restriction was put in place by the administrator for policy violations.</p>
              <div className="contact-info">
                <p><strong>Need help?</strong></p>
                <p>Please contact the system administrator for assistance or to appeal this decision.</p>
              </div>
            </div>
            <div className="modal-footer-banned">
              <button className="btn-understand" onClick={() => setShowBannedModal(false)}>
                I Understand
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Login; 