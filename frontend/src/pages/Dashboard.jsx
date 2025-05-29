import { useState, useEffect } from 'react';
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
    trash: 0
  });
  const [processedFiles, setProcessedFiles] = useState([]);
  const [processingFiles, setProcessingFiles] = useState([]);
  const [deletedFiles, setDeletedFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Đảm bảo rằng chỉ hiển thị dữ liệu trên client để tránh hydration mismatch
  useEffect(() => {
    setIsClient(true);
    
    // Fetch all necessary data when component mounts
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        
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
    if (!selectedFile) return;
    
    try {
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
      toast.error('Failed to upload file');
    }
  };
  
  return (
    <div className="page-container dashboard-page wide-dashboard">
      <div className="dashboard-header">
        <div className="header-content">
          <h1 className="no-underline">Dashboard</h1>
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
              <h2 className="no-underline">Service Status</h2>
              <div className="status-list">
                <div className="status-item">
                    <div className="status-icon">
                    <div className="heart-icon"></div>
                  </div>
                  <div className="status-info">
                    <span className="status-label">System Health</span>
                    <div className="status-value online">
                      <span className="status-dot"></span>
                      Ready
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="card storage-status">
              <h2 className="no-underline">AWS Cloud Storage Usage</h2>
              <div className="storage-usage">
                <div className="progress-container">
                  <div className="progress-bar" style={{ width: '42%' }}></div>
                </div>
                <div className="storage-info">
                  <span>8.4 GB / 20 GB Used</span>
                  <span>42%</span>
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
                        <div className="processing-indicator">
                          <div className="processing-spinner"></div>
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