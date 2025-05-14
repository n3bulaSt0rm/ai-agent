import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import '../styles/Login.css';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [fadeIn, setFadeIn] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const loginPageRef = useRef(null);

  useEffect(() => {
    // Trigger fade-in animation after component mounts
    setTimeout(() => setFadeIn(true), 100);
    
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
        setTimeout(() => navigate('/dashboard'), 300);
      } else {
        setError('Invalid username or password');
      }
    } catch (error) {
      setError(error.message || 'An error occurred during login');
    } finally {
      setIsLoading(false);
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
                  type="text"
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
              Sign in
            </button>
          </form>
        </div>
      </div>
      
      {isLoading && (
        <div className="loading-overlay">
          <div className="loading-popup">
            <span className="spinner"></span>
            <span>Signing in...</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default Login; 