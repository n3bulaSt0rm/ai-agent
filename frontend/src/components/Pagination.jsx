import React from 'react';
import '../styles/Pagination.css';

const Pagination = ({ 
  currentPage, 
  totalPages, 
  onPageChange
}) => {
  // Don't render pagination if there's only one page
  if (totalPages <= 1) return null;
  
  // Create page array to match the "< 1 2 ... 9 10 >" format
  const getPageNumbers = () => {
    const pages = [];
    
    // For 4 or fewer pages, just show all pages
    if (totalPages <= 4) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
      return pages;
    }
    
    // Always show first two pages
    pages.push(1);
    if (totalPages > 1) {
      pages.push(2);
    }
    
    // Add ellipsis if needed and not near the edges
    if (currentPage > 4 && totalPages > 5) {
      pages.push('...');
    }
    
    // Add middle pages around current page if not already included
    if (currentPage > 2 && currentPage < totalPages - 1) {
      if (currentPage > 3 && currentPage < totalPages - 2) {
        pages.push(currentPage);
      }
    }
    
    // Add ellipsis before last pages if needed
    if (currentPage < totalPages - 3 && totalPages > 5) {
      pages.push('...');
    }
    
    // Show last two pages
    if (totalPages > 2) {
      pages.push(totalPages - 1);
    }
    pages.push(totalPages);
    
    return pages;
  };

  const renderPageButton = (page) => {
    const isActive = page === currentPage;
    const isEllipsis = page === '...';
    
    if (isEllipsis) {
      return (
        <span key="ellipsis" className="pagination-ellipsis">
          {page}
        </span>
      );
    }
    
    return (
      <button
        key={page}
        className={`pagination-button ${isActive ? 'active' : ''}`}
        onClick={() => !isActive && onPageChange(page)}
        disabled={isActive}
      >
        {page}
      </button>
    );
  };

  return (
    <div className="pagination-container">
      {/* Previous button */}
      <button
        className="pagination-arrow-button"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
      >
        &lt;
      </button>

      {/* Page numbers */}
      <div className="pagination-buttons">
        {getPageNumbers().map(page => renderPageButton(page))}
      </div>

      {/* Next button */}
      <button
        className="pagination-arrow-button"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
      >
        &gt;
      </button>
    </div>
  );
};

export default Pagination; 