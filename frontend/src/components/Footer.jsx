import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/Footer.css';
import { 
  EnvelopeIcon, 
  PhoneIcon, 
  MapPinIcon 
} from '@heroicons/react/24/outline';

const Footer = () => {
  const currentYear = new Date().getFullYear();
  
  return (
    <footer className="footer">
      <div className="footer-content">
        <div className="footer-columns">
          <div className="footer-column">
            <div className="footer-logo">
              <span className="logo-text">
                <span className="primary">AI</span>
                <span className="secondary">Agent</span>
              </span>
            </div>
          </div>
          
          <div className="footer-column">
            <h3>Dashboard</h3>
            <ul>
              <li><Link to="/">Home</Link></li>
              <li><Link to="/documents">Documents</Link></li>
              <li><Link to="/analytics">Analytics</Link></li>
            </ul>
          </div>
          
          <div className="footer-column">
            <h3>Resources</h3>
            <ul>
              <li><Link to="/help">Help Center</Link></li>
              <li><Link to="/guides">Guides</Link></li>
              <li><Link to="/api">API Docs</Link></li>
            </ul>
          </div>
          
          <div className="footer-column">
            <h3>Company</h3>
            <ul>
              <li><Link to="/about">About Us</Link></li>
              <li><Link to="/careers">Careers</Link></li>
              <li><Link to="/blog">Blog</Link></li>
            </ul>
          </div>
          
          <div className="footer-column">
            <h3>Contact Us</h3>
            <div className="contact-item">
              <EnvelopeIcon className="w-4 h-4 contact-icon" />
              <p>contact@aiagent.com</p>
            </div>
            <div className="contact-item">
              <PhoneIcon className="w-4 h-4 contact-icon" />
              <p>+84 123 456 789</p>
            </div>
            <div className="contact-item">
              <MapPinIcon className="w-4 h-4 contact-icon" />
              <p>Hanoi, Vietnam</p>
            </div>
          </div>
        </div>
        
        <div className="footer-bottom">
          <p className="copyright">© {currentYear} AI Agent. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
};

export default Footer; 