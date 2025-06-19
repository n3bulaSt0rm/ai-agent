import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import '../styles/FileDetail.css';
import filesApi from '../services/api';
import { toast } from 'react-hot-toast';
import LoadingOverlay from '../components/LoadingOverlay';
import '../styles/LoadingOverlay.css';

// Import icons
import TrashIcon from '@heroicons/react/24/outline/TrashIcon';
import ArrowPathIcon from '@heroicons/react/24/outline/ArrowPathIcon';
import PencilIcon from '@heroicons/react/24/outline/PencilIcon';
import CheckIcon from '@heroicons/react/24/outline/CheckIcon';
import CalendarIcon from '@heroicons/react/24/outline/CalendarIcon';

const FileDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showProcessModal, setShowProcessModal] = useState(false);
  const [pageRanges, setPageRanges] = useState([{ start: 1, end: 1 }]);
  const [pageRangeError, setPageRangeError] = useState("");
  const [loadingAction, setLoadingAction] = useState({ isLoading: false, message: '' });
  
  // Add state for editing fields
  const [isEditingDescription, setIsEditingDescription] = useState(false);
  const [descriptionInput, setDescriptionInput] = useState('');
  const [isEditingCreatedDate, setIsEditingCreatedDate] = useState(false);
  const [createdDateInput, setCreatedDateInput] = useState('');
  const [keywordsInput, setKeywordsInput] = useState('');
  
  // Helper function to format dates in YYYY-MM-DD for input elements
  const toInputDateFormat = (dateString) => {
    if (!dateString) return '';
    
    // If already in YYYY-MM-DD format, return as is
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
      return dateString;
    }
    
    // If in DD/MM/YYYY format, convert to YYYY-MM-DD
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateString)) {
      const [day, month, year] = dateString.split('/');
      return `${year}-${month}-${day}`;
    }
    
    // Otherwise, try to parse as a date
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return ''; // Return empty if invalid date
    
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    
    return `${year}-${month}-${day}`;
  };
  
  // Helper function to format dates in DD/MM/YYYY format
  const formatDate = (dateString) => {
    if (!dateString) return '';
    
    // If already in YYYY-MM-DD format (for date input), return as is
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
      return dateString;
    }
    
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString; // Return original if invalid date
    
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    
    return `${day}/${month}/${year}`;
  };
  
  useEffect(() => {
    // Fetch document details
    const fetchDocument = async () => {
      setLoading(true);
      try {
        const data = await filesApi.getFile(parseInt(id));
        
        if (data) {
          setDocument(data);
          setDescriptionInput(data.description || '');
          setCreatedDateInput(data.fileCreatedAt || '');
          setKeywordsInput(data.keywords ? data.keywords.join(', ') : '');
          
          // If we have pages_processed_range, initialize it
          if (data.pages_processed_range) {
            try {
              // Parse the JSON string into an array
              const processedRanges = JSON.parse(data.pages_processed_range);
              console.log("Processed ranges:", processedRanges);
            } catch (e) {
              console.error("Error parsing processed ranges:", e);
            }
          }
        } else {
          // Document not found
          navigate('/files', { replace: true });
        }
      } catch (error) {
        console.error('Error fetching document:', error);
        toast.error('Failed to load document details');
        navigate('/files', { replace: true });
      } finally {
        setLoading(false);
      }
    };
    
    fetchDocument();
  }, [id, navigate]);
  
  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };
  
  const confirmDelete = async () => {
    try {
      setLoadingAction({ isLoading: true, message: 'Deleting document...' });
      setShowDeleteConfirm(false);
      
      await filesApi.deleteFile(parseInt(id));
      toast.success(`Document moved to trash`);
      
      navigate('/files', { replace: true });
    } catch (error) {
      console.error('Error deleting document:', error);
      toast.error('Failed to delete document');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  // Add function to update description
  const handleSaveDescription = async () => {
    try {
      setLoadingAction({ isLoading: true, message: 'Updating description...' });
      
      await filesApi.updateFileDescription(document.id, descriptionInput);
      
      // Update local state
      setDocument({
        ...document,
        description: descriptionInput
      });
      
      setIsEditingDescription(false);
      toast.success('Description updated successfully');
      
    } catch (error) {
      console.error('Error updating description:', error);
      toast.error('Failed to update description');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  // Add function to update file created date
  const handleSaveCreatedDate = async () => {
    try {
      setLoadingAction({ isLoading: true, message: 'Updating document creation date...' });
      
      await filesApi.updateFileCreatedAt(document.id, createdDateInput);
      
      // Update local state
      setDocument({
        ...document,
        fileCreatedAt: createdDateInput
      });
      
      setIsEditingCreatedDate(false);
      toast.success('Document creation date updated successfully');
      
    } catch (error) {
      console.error('Error updating file creation date:', error);
      toast.error('Failed to update file creation date');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  // Add function to update keywords
  const handleSaveKeywords = async () => {
    try {
      setLoadingAction({ isLoading: true, message: 'Updating keywords...' });
      
      await filesApi.updateKeywords(document.id, keywordsInput);
      
      // Update local state - parse keywords for display
      const keywordArray = keywordsInput.split(',')
        .map(k => k.trim())
        .filter(k => k);
      
      setDocument({
        ...document,
        keywords: keywordArray
      });
      
      toast.success('Keywords updated successfully');
      
    } catch (error) {
      console.error('Error updating keywords:', error);
      toast.error('Failed to update keywords');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  const handleProcess = () => {
    if (!document || !document.pages) {
      toast.error('Cannot process document without page information');
      return;
    }
    
    // Get existing processed ranges if any
    const existingRanges = [];
    if (document.pages_processed_range) {
      try {
        const ranges = JSON.parse(document.pages_processed_range);
        if (Array.isArray(ranges) && ranges.length > 0) {
          // Parse string ranges like "1-5" to objects like {start: 1, end: 5}
          ranges.forEach(rangeStr => {
            try {
              const [start, end] = rangeStr.split('-').map(num => parseInt(num, 10));
              if (!isNaN(start) && !isNaN(end)) {
                existingRanges.push({ start, end });
              }
            } catch (e) {
              console.error("Error parsing range:", rangeStr, e);
            }
          });
        }
      } catch (e) {
        console.error("Error parsing processed ranges:", e);
      }
    }
    
    // If document has no pages yet, set a default range
    if (existingRanges.length === 0) {
      // No existing ranges, process the whole document
      setPageRanges([{ start: 1, end: document.pages }]);
    } else {
      // Find unprocessed ranges
      const sortedRanges = existingRanges.sort((a, b) => a.start - b.start);
      const unprocessedRanges = [];
      
      // Check from beginning of document
      if (sortedRanges[0].start > 1) {
        unprocessedRanges.push({ start: 1, end: sortedRanges[0].start - 1 });
      }
      
      // Check between processed ranges
      for (let i = 0; i < sortedRanges.length - 1; i++) {
        if (sortedRanges[i].end + 1 < sortedRanges[i+1].start) {
          unprocessedRanges.push({
            start: sortedRanges[i].end + 1, 
            end: sortedRanges[i+1].start - 1
          });
        }
      }
      
      // Check end of document
      if (sortedRanges[sortedRanges.length - 1].end < document.pages) {
        unprocessedRanges.push({
          start: sortedRanges[sortedRanges.length - 1].end + 1,
          end: document.pages
        });
      }
      
      if (unprocessedRanges.length > 0) {
        setPageRanges(unprocessedRanges);
      } else {
        // All pages processed
        setPageRanges([]);
        setPageRangeError("All pages have been processed");
      }
    }
    
    setShowProcessModal(true);
  };
  
  const handleAddPageRange = () => {
    setPageRanges([...pageRanges, { start: 1, end: document?.pages || 1 }]);
  };
  
  const handleRemovePageRange = (index) => {
    if (pageRanges.length > 1) {
      const newRanges = [...pageRanges];
      newRanges.splice(index, 1);
      setPageRanges(newRanges);
    }
  };
  
  const handlePageRangeChange = (index, field, value) => {
    const newValue = parseInt(value, 10);
    if (isNaN(newValue) || newValue < 1) return;
    
    const newRanges = [...pageRanges];
    newRanges[index] = { ...newRanges[index], [field]: newValue };
    
    // Validate that start <= end
    if (field === 'start' && newValue > newRanges[index].end) {
      newRanges[index].end = newValue;
    } else if (field === 'end' && newValue < newRanges[index].start) {
      newRanges[index].start = newValue;
    }
    
    // Validate against document page count
    if (document?.pages) {
      if (newRanges[index].end > document.pages) {
        newRanges[index].end = document.pages;
      }
    }
    
    setPageRanges(newRanges);
    setPageRangeError("");
  };
  
  const handleConfirmProcess = async () => {
    try {
      // Validate page ranges don't overlap
      const sortedRanges = [...pageRanges].sort((a, b) => a.start - b.start);
      for (let i = 0; i < sortedRanges.length - 1; i++) {
        if (sortedRanges[i].end >= sortedRanges[i+1].start) {
          setPageRangeError("Page ranges cannot overlap");
          return;
        }
      }
      
      // Validate page ranges against existing processed ranges
      if (document.pages_processed_range) {
        try {
          const existingRangesStrings = JSON.parse(document.pages_processed_range);
          if (Array.isArray(existingRangesStrings)) {
            for (const newRange of pageRanges) {
              for (const existingRangeStr of existingRangesStrings) {
                try {
                  const [start, end] = existingRangeStr.split('-').map(num => parseInt(num, 10));
                  if (
                    (newRange.start <= end && newRange.end >= start)
                  ) {
                    setPageRangeError(`Range ${newRange.start}-${newRange.end} overlaps with already processed range ${existingRangeStr}`);
                    return;
                  }
                } catch (e) {
                  console.error("Error parsing range:", existingRangeStr, e);
                }
              }
            }
          }
        } catch (e) {
          console.error("Error validating against existing ranges:", e);
        }
      }
      
      setLoadingAction({ isLoading: true, message: 'Processing document...' });
      setShowProcessModal(false);
      
      // Convert page ranges to the string format expected by the backend
      const pageRangesStrings = pageRanges.map(range => `${range.start}-${range.end}`);
      
      await filesApi.processFile(document.id, { page_ranges: pageRangesStrings });
      toast.success(`Processing document...`);
      
      // Refresh document data
      const updatedDoc = await filesApi.getFile(parseInt(id));
      setDocument(updatedDoc);
    } catch (error) {
      console.error(`Error processing document: ${error}`);
      toast.error('Failed to process document');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  // Helper function to format processed page ranges for display
  const formatProcessedRanges = () => {
    if (!document || !document.pages_processed_range) return "None";
    
    try {
      const ranges = JSON.parse(document.pages_processed_range);
      if (!Array.isArray(ranges) || ranges.length === 0) return "None";
      
      // Sort the string ranges by their start number
      return ranges
        .sort((a, b) => {
          const [aStart] = a.split('-').map(num => parseInt(num, 10));
          const [bStart] = b.split('-').map(num => parseInt(num, 10));
          return aStart - bStart;
        })
        .join(", ");
    } catch (e) {
      console.error("Error formatting processed ranges:", e);
      return "Error parsing ranges";
    }
  };
  
  if (loading) {
    return (
      <div className="page-container file-detail">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading document details...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container file-detail">
      <LoadingOverlay 
        isVisible={loadingAction.isLoading}
        message={loadingAction.message}
      />
      
      <header className="page-header">
        <div className="header-back-button">
          <Link to="/files" className="back-button">
            <i className="back-icon"></i>
            <span>Back to all documents</span>
          </Link>
        </div>
        <div className="header-actions">
          {document && document.status === 'pending_upload' && (
            <button 
              className="btn-primary"
              onClick={handleProcess}
              disabled={document.status === 'processing'}
            >
              <ArrowPathIcon className="w-5 h-5 mr-2" />
              Process
            </button>
          )}
          <button className="btn-secondary">
            <i className="icon download-icon"></i>
            Download
          </button>
          <button className="btn-danger" onClick={handleDelete}>
            <TrashIcon className="w-5 h-5 mr-2" />
            Delete
          </button>
        </div>
      </header>
      
      <div className="document-hero">
        <div className={`document-type-large ${document?.type || 'pdf'}`}></div>
        <div className="document-hero-content">
          <h1>{document?.title}</h1>
          <div className="document-meta">
            <span className="meta-item">
              <i className="icon file-icon"></i>
              {document?.size}
            </span>
            <span className="meta-item">
              <i className="icon pages-icon"></i>
              {document?.pages} pages
            </span>
            <span className="meta-item">
              <i className="icon calendar-icon"></i>
              Uploaded on {document?.uploadAt}
            </span>
            <span className="meta-item">
              <i className="icon user-icon"></i>
              by {document?.uploadedBy}
            </span>
            <span className={`status-badge ${document?.status}`}>
              {document?.status === 'processed' ? 'Processed' : 
               document?.status === 'processing' ? 'Processing' : 'Pending'}
            </span>
          </div>
        </div>
      </div>
      
      <div className="document-tabs">
        <button 
          className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button 
          className={`tab-button ${activeTab === 'content' ? 'active' : ''}`}
          onClick={() => setActiveTab('content')}
        >
          Content
        </button>
        <button 
          className={`tab-button ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => setActiveTab('insights')}
        >
          AI Insights
        </button>
      </div>
      
      <div className="document-tab-content">
        {activeTab === 'overview' && (
          <div className="tab-pane overview-tab">
            <div className="document-card">
              <div className="card-header">
                <h2>Document Information</h2>
              </div>
              
              {isEditingDescription ? (
                <div className="edit-description">
                  <textarea
                    value={descriptionInput}
                    onChange={(e) => setDescriptionInput(e.target.value)}
                    className="description-textarea"
                    rows={4}
                    placeholder="Enter document description..."
                  />
                  <div className="edit-actions">
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => {
                        setIsEditingDescription(false);
                        setDescriptionInput(document.description || '');
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn-primary btn-sm"
                      onClick={handleSaveDescription}
                    >
                      <CheckIcon className="w-4 h-4 mr-1" />
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className="description-section">
                  <div className="description-header">
                    <h3>Description</h3>
                    <button
                      className="btn-icon"
                      onClick={() => setIsEditingDescription(true)}
                      title="Edit description"
                    >
                      <PencilIcon className="w-4 h-4" />
                    </button>
                  </div>
                  <p className="document-description">
                    {document.description || "No description available"}
                  </p>
                </div>
              )}
              
              <div className="document-details">
                <div className="detail-row">
                  <div className="detail-label">File type</div>
                  <div className="detail-value">{document.type.toUpperCase()} Document</div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Size</div>
                  <div className="detail-value">{document.size}</div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Pages</div>
                  <div className="detail-value">{document.pages}</div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Processed Pages</div>
                  <div className="detail-value">{formatProcessedRanges()}</div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Upload date</div>
                  <div className="detail-value">{formatDate(document.uploadAt)}</div>
                </div>
                
                <div className="detail-row">
                  <div className="detail-label">Document Creation Date</div>
                  <div className="detail-value-group">
                    <div className="detail-value">{formatDate(document.fileCreatedAt)}</div>
                    <button
                      className="btn-icon"
                      onClick={() => setIsEditingCreatedDate(true)}
                      title="Edit document creation date"
                    >
                      <PencilIcon className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                
                {isEditingCreatedDate && (
                  <div className="edit-date">
                    <div className="date-input-group">
                      <input
                        type="date"
                        value={toInputDateFormat(createdDateInput)}
                        onChange={(e) => setCreatedDateInput(e.target.value)}
                        className="date-input"
                      />
                      <div className="edit-actions">
                        <button
                          className="btn-secondary btn-sm"
                          onClick={() => {
                            setIsEditingCreatedDate(false);
                            setCreatedDateInput(document.fileCreatedAt || '');
                          }}
                        >
                          Cancel
                        </button>
                        <button
                          className="btn-primary btn-sm"
                          onClick={handleSaveCreatedDate}
                        >
                          <CalendarIcon className="w-4 h-4 mr-1" />
                          Update Current Date
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                
                <div className="detail-row">
                  <div className="detail-label">Uploaded By</div>
                  <div className="detail-value">{document.uploadedBy || 'admin'}</div>
                </div>
                
                {/* Show source field only for txt files */}
                {document.type === 'txt' && document.source && (
                  <div className="detail-row">
                    <div className="detail-label">Source</div>
                    <div className="detail-value" style={{ 
                      wordBreak: 'break-all',
                      fontSize: '14px',
                      color: '#1e293b'
                    }}>
                      {document.source}
                    </div>
                  </div>
                )}
                
                {/* Keywords section - hidden but logic maintained */}
                <div className="detail-row" style={{ display: 'none' }}>
                  <div className="detail-label">Keywords</div>
                  <div className="detail-value keywords-container">
                    <div className="keyword-tags">
                      {document.keywords && document.keywords.length > 0
                        ? document.keywords.map((keyword, index) => (
                            <span key={index} className="keyword-tag">{keyword}</span>
                          ))
                        : "No keywords"}
                    </div>
                    <button
                      className="btn-icon"
                      onClick={() => document.querySelector('#keywordsEdit').classList.toggle('show')}
                      title="Edit keywords"
                    >
                      <PencilIcon className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                
                {/* Keywords edit section - hidden but logic maintained */}
                <div id="keywordsEdit" className="keywords-edit" style={{ display: 'none' }}>
                  <input
                    type="text"
                    value={keywordsInput}
                    onChange={(e) => setKeywordsInput(e.target.value)}
                    placeholder="Enter keywords separated by commas"
                    className="keywords-input"
                  />
                  <div className="edit-actions">
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => {
                        document.querySelector('#keywordsEdit').classList.remove('show');
                        setKeywordsInput(document.keywords ? document.keywords.join(', ') : '');
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => {
                        handleSaveKeywords();
                        document.querySelector('#keywordsEdit').classList.remove('show');
                      }}
                    >
                      <CheckIcon className="w-4 h-4 mr-1" />
                      Save Keywords
                    </button>
                  </div>
                </div>
                
                <div className="detail-row">
                  <div className="detail-label">Status</div>
                  <div className="detail-value">
                    <span className={`status-badge ${document.status}`}>
                      {document.status === 'processed' ? 'Processed' : 
                       document.status === 'processing' ? 'Processing' : 'Pending'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="document-card">
              <h2>Processing Information</h2>
              <div className="processing-info">
                <div className="processing-item">
                  <div className="processing-icon ocr"></div>
                  <div className="processing-content">
                    <h3>OCR Processing</h3>
                    <p>Text extraction complete with 98% accuracy</p>
                    <div className="progress-bar">
                      <div className="progress-value" style={{ width: '100%' }}></div>
                    </div>
                  </div>
                </div>
                
                <div className="processing-item">
                  <div className="processing-icon embedding"></div>
                  <div className="processing-content">
                    <h3>Embeddings Generation</h3>
                    <p>Vector embeddings created for intelligent search</p>
                    <div className="progress-bar">
                      <div className="progress-value" style={{ width: '100%' }}></div>
                    </div>
                  </div>
                </div>
                
                <div className="processing-item">
                  <div className="processing-icon analysis"></div>
                  <div className="processing-content">
                    <h3>AI Document Analysis</h3>
                    <p>Key topics and insights extracted</p>
                    <div className="progress-bar">
                      <div className="progress-value" style={{ width: '100%' }}></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {activeTab === 'content' && (
          <div className="tab-pane content-tab">
            <div className="document-toolbar">
              <div className="toolbar-section">
                <input 
                  type="text" 
                  placeholder="Search within document..." 
                  className="document-search-input"
                />
              </div>
              <div className="toolbar-section">
                <label className="toolbar-label">Page:</label>
                <select className="toolbar-select">
                  {Array.from({ length: document.pages }, (_, i) => (
                    <option key={i + 1} value={i + 1}>
                      {i + 1} of {document.pages}
                    </option>
                  ))}
                </select>
                
                <div className="toolbar-buttons">
                  <button className="toolbar-button" title="Previous page">
                    <i className="prev-icon"></i>
                  </button>
                  <button className="toolbar-button" title="Next page">
                    <i className="next-icon"></i>
                  </button>
                </div>
                
                <div className="toolbar-zoom">
                  <button className="toolbar-button" title="Zoom out">
                    <i className="zoom-out-icon"></i>
                  </button>
                  <span className="zoom-level">100%</span>
                  <button className="toolbar-button" title="Zoom in">
                    <i className="zoom-in-icon"></i>
                  </button>
                </div>
              </div>
            </div>
            
            <div className="document-preview-container">
              <div className="document-preview">
                <div className="document-page">
                  {document.sampleContent && document.sampleContent.map((content, index) => (
                    <div key={index} className="page-content">
                      <div className="page-number">Page {content.page}</div>
                      <pre className="page-text">{content.text}</pre>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
        
        {activeTab === 'insights' && (
          <div className="tab-pane insights-tab">
            <div className="insights-container">
              <div className="insight-card">
                <h2>Key Topics</h2>
                <div className="topics-list">
                  <div className="topic-item">
                    <div className="topic-name">Đào tạo tín chỉ</div>
                    <div className="topic-bar">
                      <div className="topic-progress" style={{ width: '85%' }}></div>
                    </div>
                    <div className="topic-percentage">85%</div>
                  </div>
                  <div className="topic-item">
                    <div className="topic-name">Quy định học vụ</div>
                    <div className="topic-bar">
                      <div className="topic-progress" style={{ width: '72%' }}></div>
                    </div>
                    <div className="topic-percentage">72%</div>
                  </div>
                  <div className="topic-item">
                    <div className="topic-name">Đánh giá kết quả</div>
                    <div className="topic-bar">
                      <div className="topic-progress" style={{ width: '68%' }}></div>
                    </div>
                    <div className="topic-percentage">68%</div>
                  </div>
                  <div className="topic-item">
                    <div className="topic-name">Tốt nghiệp</div>
                    <div className="topic-bar">
                      <div className="topic-progress" style={{ width: '55%' }}></div>
                    </div>
                    <div className="topic-percentage">55%</div>
                  </div>
                </div>
              </div>
              
              <div className="insight-card">
                <h2>Document Summary</h2>
                <p className="summary-text">
                  Tài liệu này quy định chi tiết về quy chế đào tạo đại học theo hệ thống tín chỉ 
                  tại trường Đại học Bách khoa Hà Nội. Quy chế bao gồm các nội dung về chương trình 
                  đào tạo, tổ chức đào tạo, kiểm tra và thi học phần, xét và công nhận tốt nghiệp.
                </p>
                <p className="summary-text">
                  Đặc biệt, tài liệu nhấn mạnh vào phương pháp đánh giá kết quả học tập của sinh viên
                  với các hình thức kiểm tra đa dạng. Quy chế cũng đưa ra các quy định cụ thể về điều 
                  kiện được học tiếp, cảnh báo học tập, buộc thôi học và điều kiện xét tốt nghiệp.
                </p>
              </div>
              
              <div className="insight-card">
                <h2>Ask AI about this document</h2>
                <div className="ai-query-box">
                  <input 
                    type="text" 
                    placeholder="Ask a question about this document..." 
                    className="ai-query-input"
                  />
                  <button className="btn-primary ai-query-button">
                    <i className="ai-icon"></i>
                    Ask AI
                  </button>
                </div>
                
                <div className="sample-queries">
                  <p className="sample-heading">Try asking:</p>
                  <div className="sample-buttons">
                    <button className="sample-query">Điều kiện tốt nghiệp là gì?</button>
                    <button className="sample-query">Quy định về kiểm tra đánh giá?</button>
                    <button className="sample-query">Cách tính điểm trung bình học kỳ?</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      
      {/* Confirm Delete Modal */}
      {showDeleteConfirm && (
        <div className="modal-container">
          <div className="modal">
            <div className="modal-header">
              <h2>Delete Document</h2>
              <button className="close-button" onClick={() => setShowDeleteConfirm(false)}>×</button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to delete "{document.title}"?</p>
              <p>The document will be moved to trash.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowDeleteConfirm(false)}>Cancel</button>
              <button className="btn-danger" onClick={confirmDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
      
      {/* Process Page Range Modal */}
      {showProcessModal && document && (
        <div className="modal-container">
          <div className="modal">
            <div className="modal-header">
              <h2>Process Document: {document.title}</h2>
              <button className="close-button" onClick={() => setShowProcessModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <p>Select page ranges to process (Document has {document.pages || "unknown"} pages)</p>
              
              {pageRangeError && (
                <div className="error-message">{pageRangeError}</div>
              )}
              
              {pageRanges.length > 0 ? (
                pageRanges.map((range, index) => (
                  <div className="page-range-row" key={index}>
                    <div className="range-inputs">
                      <label>
                        Start:
                        <input 
                          type="number" 
                          min="1" 
                          max={document.pages || 1}
                          value={range.start}
                          onChange={(e) => handlePageRangeChange(index, 'start', e.target.value)}
                        />
                      </label>
                      <label>
                        End:
                        <input 
                          type="number" 
                          min={range.start} 
                          max={document.pages || 1}
                          value={range.end}
                          onChange={(e) => handlePageRangeChange(index, 'end', e.target.value)}
                        />
                      </label>
                    </div>
                    <button 
                      className="btn-icon" 
                      onClick={() => handleRemovePageRange(index)}
                      disabled={pageRanges.length <= 1}
                    >
                      <TrashIcon className="h-5 w-5" />
                    </button>
                  </div>
                ))
              ) : (
                <p>All pages have been processed</p>
              )}
              
              <div className="modal-actions">
                <button 
                  className="btn-secondary" 
                  onClick={handleAddPageRange}
                  disabled={pageRanges.length === 0}
                >
                  Add Range
                </button>
              </div>
            </div>
            <div className="modal-footer">
              <button 
                className="btn-secondary" 
                onClick={() => setShowProcessModal(false)}
              >
                Cancel
              </button>
              <button 
                className="btn-primary" 
                onClick={handleConfirmProcess}
                disabled={pageRanges.length === 0 || pageRangeError}
              >
                Process
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileDetail; 