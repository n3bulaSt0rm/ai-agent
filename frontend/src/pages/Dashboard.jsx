import { useState, useEffect, useRef } from 'react';
import '../styles/Dashboard.css';
import ArrowUpTrayIcon from '@heroicons/react/24/outline/ArrowUpTrayIcon';
import FileUploader from '../components/FileUploader';
import { toast } from 'react-hot-toast';
import filesApi from '../services/api';

const Dashboard = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isClient, setIsClient] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileStats, setFileStats] = useState({
    total: 0,
    pending: 0,
    processing: 0,
    processed: 0,
    trash: 0,
    storage: {
      used_mb: 0,
      limit_mb: 1000,
      percentage: 0
    }
  });
  const [processedFiles, setProcessedFiles] = useState([]);
  const [processingFiles, setProcessingFiles] = useState([]);
  const [deletedFiles, setDeletedFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [serviceHealth, setServiceHealth] = useState({
    status: 'loading',
    timestamp: null,
    message: 'Checking system health...'
  });
  
  // Health check interval reference
  const healthCheckIntervalRef = useRef(null);
  
  // Function to check service health
  const checkServiceHealth = async () => {
    try {
      const healthStatus = await filesApi.getProcessingServiceHealth();
      setServiceHealth({
        status: healthStatus.status || 'unknown',
        timestamp: healthStatus.timestamp || new Date().toISOString(),
        message: healthStatus.message || 'System health check completed'
      });
      
      // Add a console log to show the health check result
      console.log("Processing service health status:", healthStatus);
    } catch (error) {
      console.error('Health check failed:', error);
      setServiceHealth({
        status: 'error',
        timestamp: new Date().toISOString(),
        message: 'Failed to check system health'
      });
    }
  };
  
  // Đảm bảo rằng chỉ hiển thị dữ liệu trên client để tránh hydration mismatch
  useEffect(() => {
    setIsClient(true);
    
    // Fetch all necessary data when component mounts
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        
        // Check service health immediately on load
        await checkServiceHealth();
        
        // Start health check interval (every 60 seconds)
        healthCheckIntervalRef.current = setInterval(checkServiceHealth, 60000);
        
        // Fetch statistics
        const stats = await filesApi.getFileStats();
        setFileStats(stats);
        
        // Fetch recently processed files (limit to 3)
        const processedResponse = await filesApi.getFiles(3, 0, "processed");
        setProcessedFiles(processedResponse.files || []);
        
        // Fetch currently processing files (limit to 3)
        const processingResponse = await filesApi.getFiles(3, 0, "processing");
        setProcessingFiles(processingResponse.files || []);
        
        // Fetch recently deleted files (limit to 3)
        const deletedResponse = await filesApi.getFiles(3, 0, "deleted");
        setDeletedFiles(deletedResponse.files || []);
        
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
        toast.error('Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    };
    
    fetchDashboardData();
    
    // Cleanup interval on component unmount
    return () => {
      if (healthCheckIntervalRef.current) {
        clearInterval(healthCheckIntervalRef.current);
      }
    };
  }, []);
  
  // Helper function to format dates in DD/MM/YYYY format
  const formatDate = (dateString) => {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString; // Return original if invalid date
    
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    
    return `${day}/${month}/${year}`;
  };
  
  const handleFileSelected = (file) => {
    setSelectedFile(file);
  };
  
  const handleUpload = async () => {
    if (!selectedFile) {
      console.error('No file selected for upload');
      toast.error('Please select a file to upload');
      return;
    }
    
    try {
      console.log('Dashboard - Uploading file:', selectedFile.name);
      console.log('Dashboard - File object type:', selectedFile instanceof File ? 'File object' : typeof selectedFile);
      console.log('Dashboard - File metadata:', {
        name: selectedFile.name,
        size: selectedFile.size,
        type: selectedFile.type,
        createdAt: selectedFile.fileCreatedAt,
        keywords: selectedFile.keywords
      });
      
      const response = await filesApi.uploadFile(
        selectedFile,
        selectedFile.description || '',
        selectedFile.fileCreatedAt,
        selectedFile.keywords
      );
      
      toast.success(`"${selectedFile.name}" uploaded successfully.`);
      
      // Refresh data after upload
      const stats = await filesApi.getFileStats();
      setFileStats(stats);
      
      // Close modal and reset state
      setIsModalOpen(false);
      setSelectedFile(null);
    } catch (error) {
      console.error('Error uploading file:', error);
      toast.error('Failed to upload file: ' + (error.message || 'Unknown error'));
    }
  };
  
  return (
    <div className="page-container dashboard-page wide-dashboard">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>Monitor your document management system</p>
        </div>
        <div className="header-actions">
          <button className="btn-primary" onClick={() => setIsClient && setIsModalOpen(true)}>
            <ArrowUpTrayIcon className="w-5 h-5 mr-2" />
            Upload
          </button>
        </div>
      </div>
      
      {isClient && (
        <>
          <div className="stats-overview">
            <div className="stat-card gradient-card">
              <div className="stat-icon document-icon"></div>
              <div className="stat-content">
                <h3>{loading ? '...' : fileStats.total}</h3>
                <p>Total Documents</p>
              </div>
            </div>
            
            <div className="stat-card processing-card">
              <div className="stat-icon processing-doc-icon"></div>
              <div className="stat-content">
                <h3>{loading ? '...' : fileStats.processing}</h3>
                <p>Processing Documents</p>
              </div>
            </div>
            
            <div className="stat-card accent-card">
              <div className="stat-icon page-icon"></div>
              <div className="stat-content">
                <h3>{loading ? '...' : fileStats.processed}</h3>
                <p>Processed Documents</p>
              </div>
            </div>
          </div>
          
          <div className="service-row">
            <div className="card service-status">
              <h2 className="no-underline">AI Agent Status</h2>
              <div className="status-list">
                <div className="status-item">
                    <div className="status-icon">
                    <div className="heart-icon"></div>
                  </div>
                  <div className="status-info">
                    <span className="status-label">System Health</span>
                    <div className={`status-value ${serviceHealth.status === 'online' ? 'online' : 
                                                   serviceHealth.status === 'degraded' ? 'degraded' : 
                                                   serviceHealth.status === 'offline' ? 'offline' : 
                                                   'unknown'}`}>
                      <span className="status-dot"></span>
                      {serviceHealth.status === 'online' ? 'Ready' : 
                       serviceHealth.status === 'degraded' ? 'Degraded' : 
                       serviceHealth.status === 'offline' ? 'Offline' : 
                       serviceHealth.status === 'loading' ? 'Checking...' : 'Unknown'}
                    </div>
                    {serviceHealth.status !== 'online' && serviceHealth.message && (
                      <div className="status-message">{serviceHealth.message}</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
            
            <div className="card storage-status">
              <h2 className="no-underline">AWS Cloud Storage Usage</h2>
              <div className="storage-usage">
                <div className="progress-container">
                  <div className="progress-bar" style={{ width: `${fileStats.storage?.percentage || 0}%` }}></div>
                </div>
                <div className="storage-info">
                  <span>{fileStats.storage?.used_mb || 0} MB / {fileStats.storage?.limit_mb || 1000} MB Used</span>
                  <span>{fileStats.storage?.percentage || 0}%</span>
                </div>
              </div>
            </div>
          </div>
          
          <div className="documents-section">
            <div className="documents-row documents-three-columns">
              <div className="card document-card">
                <h2 className="no-underline">Recently Processed</h2>
                <div className="history-list">
                  {loading ? (
                    <div className="loading-indicator">Loading...</div>
                  ) : processedFiles.length > 0 ? (
                    processedFiles.map(doc => (
                      <div className="history-item enhanced" key={doc.id}>
                        <div className="history-icon"></div>
                        <div className="history-details">
                          <div className="history-title">{doc.title}</div>
                          <div className="history-meta">
                            <span className="meta-item">
                              <i className="size-icon"></i>
                              {doc.size}
                            </span>
                            <span className="meta-item">
                              <i className="pages-icon"></i>
                              {doc.pages} pages
                            </span>
                            <span className="meta-item">
                              <i className="date-icon"></i>
                              {formatDate(doc.uploadAt)}
                            </span>
                          </div>
                        </div>
                        <div className="history-status completed">
                          <i className="complete-icon"></i>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">
                      <p>No processed documents found</p>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="card document-card">
                <h2 className="no-underline">Currently Processing</h2>
                <div className="history-list">
                  {loading ? (
                    <div className="loading-indicator">Loading...</div>
                  ) : processingFiles.length > 0 ? (
                    processingFiles.map(doc => (
                      <div className="history-item processing-item enhanced" key={doc.id}>
                        <div className="history-icon"></div>
                        <div className="history-details">
                          <div className="history-title">{doc.title}</div>
                          <div className="history-meta">
                            <span className="meta-item">
                              <i className="size-icon"></i>
                              {doc.size}
                            </span>
                            <span className="meta-item">
                              <i className="pages-icon"></i>
                              {doc.pages} pages
                            </span>
                            <span className="meta-item">
                              <i className="date-icon"></i>
                              {formatDate(doc.uploadAt)}
                            </span>
                          </div>
                        </div>
                        <div className="processing-badge">
                          <i className="processing-icon-circle"></i>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">
                      <p>No documents are currently being processed</p>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="card document-card">
                <h2 className="no-underline">Recently Deleted</h2>
                <div className="history-list">
                  {loading ? (
                    <div className="loading-indicator">Loading...</div>
                  ) : deletedFiles.length > 0 ? (
                    deletedFiles.map(doc => (
                      <div className="history-item deleted-item enhanced" key={doc.id}>
                        <div className="history-icon"></div>
                        <div className="history-details">
                          <div className="history-title">{doc.title}</div>
                          <div className="history-meta">
                            <span className="meta-item">
                              <i className="size-icon"></i>
                              {doc.size}
                            </span>
                            <span className="meta-item">
                              <i className="pages-icon"></i>
                              {doc.pages} pages
                            </span>
                            <span className="meta-item">
                              <i className="date-icon"></i>
                              {formatDate(doc.deletedDate || doc.uploadAt)}
                            </span>
                          </div>
                        </div>
                        <div className="deleted-indicator">
                          <i className="trash-icon"></i>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">
                      <p>No deleted documents found</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
      
      {isModalOpen && (
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Upload New Document</h2>
              <button className="close-btn" onClick={() => setIsModalOpen(false)}>×</button>
            </div>
            <div className="modal-body">
              <FileUploader 
                onFileSelected={handleFileSelected}
                acceptedFormats={['.pdf', '.docx', '.doc']}
                maxSize={10}
              />
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setIsModalOpen(false)}>Cancel</button>
              <button 
                className="btn-primary" 
                disabled={!selectedFile}
                onClick={handleUpload}
              >
                Upload
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard; 