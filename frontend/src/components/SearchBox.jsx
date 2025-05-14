import React from 'react';
import '../styles/FilesList.css';

const SearchBox = ({ placeholder = "Search...", onChange, withLabel = false }) => {
  return (
    <div className={`search-box ${withLabel ? 'with-label' : ''}`}>
      <div className="search-icon-wrapper">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="search-icon-svg">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        {withLabel && <span className="search-label">Search</span>}
      </div>
      <input 
        type="text" 
        placeholder={placeholder} 
        onChange={onChange}
        className="search-input"
      />
    </div>
  );
};

export default SearchBox; 