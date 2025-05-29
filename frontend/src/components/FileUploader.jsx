import { useRef, useState } from 'react';
import { ArrowUpTrayIcon } from '@heroicons/react/24/outline';
import '../styles/FileUploader.css';

/**
 * Reusable file upload component with custom styling
 * @param {Function} onFileSelected - Callback when file is selected
 * @param {Array} acceptedFormats - Array of accepted file extensions (e.g. ['.pdf', '.docx'])
 * @param {Number} maxSize - Maximum file size in MB
 */
const FileUploader = ({ 
  onFileSelected, 
  acceptedFormats = ['.pdf', '.docx', '.txt'], 
  maxSize = 20,
  buttonText = "Upload Document"
}) => {
  const fileInputRef = useRef(null);
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [fileCreatedAt, setFileCreatedAt] = useState('');
  const [keywords, setKeywords] = useState('');

  // Handle click on the custom button
  const handleButtonClick = () => {
    fileInputRef.current.click();
  };

  // Handle file change from input
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    processFile(file);
  };

  // Handle keywords change
  const handleKeywordsChange = (e) => {
    setKeywords(e.target.value);
  };

  // Handle date change
  const handleDateChange = (e) => {
    setFileCreatedAt(e.target.value);
  };

  // Handle drag events
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  // Handle drop event
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  // Process and validate file
  const processFile = (file) => {
    if (!file) return;
    
    // Validate file size
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > maxSize) {
      setErrorMessage(`File size exceeds the ${maxSize}MB limit`);
      return;
    }

    // Validate file type
    const fileExt = '.' + file.name.split('.').pop().toLowerCase();
    if (!acceptedFormats.includes(fileExt)) {
      setErrorMessage(`File type not supported. Accepted formats: ${acceptedFormats.join(', ')}`);
      return;
    }

    // Clear any previous errors
    setErrorMessage('');
    setSelectedFile(file);
    
    // Call the callback function
    if (onFileSelected) {
      // Parse keywords into array
      const keywordArray = keywords ? keywords.split(',').map(k => k.trim()).filter(k => k) : [];
      
      // Add additional metadata to file object
      file.fileCreatedAt = fileCreatedAt || '';
      file.keywords = keywordArray;
      
      onFileSelected(file);
    }
  };

  return (
    <div className="file-uploader-container">
      <div 
        className={`file-drop-area ${dragActive ? 'drag-active' : ''}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
      >
        {!selectedFile ? (
          <>
            <div className="upload-icon-wrapper">
              <ArrowUpTrayIcon className="upload-icon" />
            </div>
            <h3>Drag & Drop Files Here</h3>
            <p>or</p>
            <button 
              type="button"
              className="upload-button"
              onClick={handleButtonClick}
            >
              Browse Files
            </button>
            <p className="file-info">
              Max file size: {maxSize}MB. Supported formats: {acceptedFormats.join(', ')}
            </p>
          </>
        ) : (
          <div className="selected-file">
            <div className="file-preview">
              <div className="file-icon"></div>
              <div className="file-details">
                <p className="file-name">{selectedFile.name}</p>
                <p className="file-size">{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB</p>
              </div>
            </div>
            
            <div className="file-metadata">
              <div className="form-group">
                <label htmlFor="fileCreatedAt">File Created Date:</label>
                <input 
                  type="date" 
                  id="fileCreatedAt" 
                  value={fileCreatedAt} 
                  onChange={handleDateChange}
                  className="form-control"
                  style={{ color: "#000000" }}
                />
              </div>
              
              <div className="form-group">
                <label htmlFor="keywords">Keywords (comma separated):</label>
                <input 
                  type="text" 
                  id="keywords" 
                  value={keywords}
                  onChange={handleKeywordsChange}
                  placeholder="Enter keywords separated by commas"
                  className="form-control"
                  style={{ color: "#000000" }}
                />
              </div>
            </div>
            
            <button 
              type="button" 
              className="change-file-btn"
              onClick={handleButtonClick}
            >
              Change File
            </button>
          </div>
        )}
        {errorMessage && <p className="error-message">{errorMessage}</p>}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept={acceptedFormats.join(',')}
          style={{ display: 'none' }}
        />
      </div>
    </div>
  );
};

export default FileUploader; 