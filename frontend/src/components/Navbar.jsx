import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import '../styles/Navbar.css';

const Navbar = () => {
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isClient, setIsClient] = useState(false);

  // Xử lý client-side rendering
  useEffect(() => {
    setIsClient(true);
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined') { // Đảm bảo chỉ chạy ở client
      const handleScroll = () => {
        if (window.scrollY > 10) {
          setIsScrolled(true);
        } else {
          setIsScrolled(false);
        }
      };
  
      window.addEventListener('scroll', handleScroll);
      return () => window.removeEventListener('scroll', handleScroll);
    }
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  // Close mobile menu when navigating
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  if (!isAuthenticated) return null;

  return (
    <nav className={`navbar ${isClient && isScrolled ? 'scrolled' : ''}`}>
      <div className="navbar-container">
        <div className="navbar-logo">
          <Link to="/dashboard">
            <div className="logo-text">
              <span className="primary">AI</span>
              <span className="primary">Agent</span>
            </div>
          </Link>
        </div>
        
        <div className={`navbar-actions ${isMobileMenuOpen ? 'active' : ''}`}>
          <Link 
            to="/dashboard" 
            className={`nav-link logout-button styled-button ${location.pathname === '/dashboard' ? 'active' : ''}`}
          >
            <i className="dashboard-icon"></i>
            Dashboard
          </Link>
          <Link 
            to="/files" 
            className={`nav-link logout-button styled-button ${location.pathname === '/files' ? 'active' : ''}`}
          >
            <i className="files-icon"></i>
            Documents
          </Link>
          <button onClick={handleLogout} className="logout-button styled-button">
            <i className="logout-icon"></i>
            <span className="logout-text">Logout</span>
          </button>
          <button className="mobile-menu-button" onClick={toggleMobileMenu}>
            <div className={`hamburger ${isMobileMenuOpen ? 'active' : ''}`}>
              <span></span>
              <span></span>
              <span></span>
            </div>
          </button>
        </div>
      </div>
    </nav>
  );
};

export default Navbar; 