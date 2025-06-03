import React from 'react';

/**
 * LoadingOverlay component that displays a full-screen loading indicator
 * @param {boolean} isVisible - Controls visibility of the overlay
 * @param {string} message - Optional message to display under the spinner
 */
const LoadingOverlay = ({ isVisible = false, message = 'Loading...' }) => {
  if (!isVisible) return null;

  return (
    <div className="loading-overlay">
      <div className="loading-content">
        <svg 
          className="loading-spinner"
          viewBox="0 0 50 50"
        >
          <circle
            cx="25"
            cy="25"
            r="20"
            fill="none"
            strokeWidth="4"
          />
        </svg>
        {message && <p className="loading-message">{message}</p>}
      </div>
    </div>
  );
};

export default LoadingOverlay; 