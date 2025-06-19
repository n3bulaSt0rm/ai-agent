import { useRef, useState, useEffect } from 'react';
import { ArrowUpTrayIcon } from '@heroicons/react/24/outline';
import '../styles/FileUploader.css';
import '../styles/LoadingOverlay.css';

// CSS for required field indicators and error messages
const requiredFieldStyles = `
  .required-field {
    color: red;
    margin-left: 4px;
  }
  
  .field-error {
    color: red;
    font-size: 12px;
    margin-top: 4px;
    margin-bottom: 0;
  }

  .field-error-highlight {
    border: 2px solid red !important;
    animation: shake 0.5s linear;
  }

  @keyframes shake {
    0% { transform: translateX(0); }
    25% { transform: translateX(-5px); }
    50% { transform: translateX(5px); }
    75% { transform: translateX(-5px); }
    100% { transform: translateX(0); }
  }
`;

/**
 * Reusable file upload component with custom styling
 * @param {Function} onFileSelected - Callback when file is selected
 * @param {Array} acceptedFormats - Array of accepted file extensions (e.g. ['.pdf', '.docx'])
 * @param {Number} maxSize - Maximum file size in MB
 */
const FileUploader = ({ 
  onFileSelected, 
  acceptedFormats = ['.pdf', '.txt'], 
  maxSize = 20,
  buttonText = "Upload Document"
}) => {
  const fileInputRef = useRef(null);
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [fileCreatedAt, setFileCreatedAt] = useState('');
  const [keywords, setKeywords] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [description, setDescription] = useState('');
  const [source, setSource] = useState('');

  // Use effect to update parent component when metadata changes
  useEffect(() => {
    if (selectedFile) {
      updateFileMetadata(false);
    }
  }, [keywords, fileCreatedAt, description, source]);

  // Add a function to highlight the date field with an error
  const highlightDateField = () => {
    const dateField = document.getElementById('fileCreatedAt');
    if (dateField) {
      dateField.classList.add('field-error-highlight');
      // Remove the highlight after 2 seconds
      setTimeout(() => {
        dateField.classList.remove('field-error-highlight');
      }, 2000);
    }
  };

  // Update metadata and notify parent
  const updateFileMetadata = (showProcessing = true) => {
    if (!selectedFile) return false;
    
    // Clear any previous errors
    setErrorMessage('');
    
    // Show processing indicator only if explicitly requested
    if (showProcessing) {
      setIsProcessing(true);
    }
    
    // Clone the file object to avoid modification issues
    const fileWithMetadata = new File([selectedFile], selectedFile.name, {
      type: selectedFile.type,
      lastModified: selectedFile.lastModified
    });
    
    // Add metadata
    fileWithMetadata.fileCreatedAt = fileCreatedAt || '';
    fileWithMetadata.description = description || '';
    fileWithMetadata.keywords = keywords || '';
    fileWithMetadata.source = source || '';
    
    console.log('Updating file with keywords:', keywords);
    console.log('Updating file with date:', fileCreatedAt);
    console.log('Updating file with description:', description);
        
    // Update the selected file
    setSelectedFile(fileWithMetadata);
    
    // Notify parent component
    onFileSelected(fileWithMetadata);
    
    // Hide processing indicator if it was shown
    if (showProcessing) {
      setTimeout(() => setIsProcessing(false), 500);
    }
    
    return true;
  };

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

  // Handle description change
  const handleDescriptionChange = (e) => {
    setDescription(e.target.value);
  };

  // Handle source change
  const handleSourceChange = (e) => {
    setSource(e.target.value);
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
    
    setIsProcessing(true);
    
    // Validate file size
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > maxSize) {
      setErrorMessage(`File size exceeds the ${maxSize}MB limit`);
      setIsProcessing(false);
      return;
    }

    // Validate file type
    const fileExt = '.' + file.name.split('.').pop().toLowerCase();
    if (!acceptedFormats.includes(fileExt)) {
      setErrorMessage(`File type not supported. Accepted formats: ${acceptedFormats.join(', ')}`);
      setIsProcessing(false);
      return;
    }

    // Clear any previous errors
    setErrorMessage('');
    
    // Create a new File object with metadata
    const fileWithMetadata = new File([file], file.name, {
      type: file.type,
      lastModified: file.lastModified
    });
    
    // Add metadata - make sure fileCreatedAt exists, even if empty
    fileWithMetadata.fileCreatedAt = fileCreatedAt || '';
    fileWithMetadata.description = description || '';
    fileWithMetadata.keywords = keywords || '';
    fileWithMetadata.source = source || '';
    
    console.log('Setting file with keywords:', keywords);
    console.log('Setting file with date:', fileCreatedAt);
    console.log('Setting file with description:', description);
    console.log('File size is automatically set:', fileWithMetadata.size);
    
    // Update state
    setSelectedFile(fileWithMetadata);
    
    // Call the callback function
    if (onFileSelected) {
      onFileSelected(fileWithMetadata);
    }
    
    // Hide processing indicator after a short delay
    setTimeout(() => setIsProcessing(false), 500);
  };

  return (
    <div className="file-uploader-container">
      {/* Inject required field styles */}
      <style>{requiredFieldStyles}</style>
      
      <div 
        className={`file-drop-area ${dragActive ? 'drag-active' : ''} ${isProcessing ? 'processing' : ''}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
      >
        {isProcessing && (
          <div className="file-processing-overlay">
            <div className="processing-spinner"></div>
            <p>Loading...</p>
          </div>
        )}
      
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
                <label htmlFor="fileCreatedAt">Document Creation Date: <span className="required-field">*</span></label>
                <input 
                  type="date" 
                  id="fileCreatedAt" 
                  value={fileCreatedAt} 
                  onChange={handleDateChange}
                  className="form-control"
                  style={{ color: "#000000" }}
                  required
                />
              </div>
              
              <div className="form-group">
                <label htmlFor="description">Description:</label>
                <textarea 
                  id="description" 
                  value={description}
                  onChange={handleDescriptionChange}
                  placeholder="Enter document description..."
                  className="form-control"
                  style={{ 
                    color: "#000000",
                    border: "1px solid #e2e8f0",
                    borderRadius: "4px",
                    padding: "8px",
                    minHeight: "80px",
                    resize: "vertical",
                    width: "100%"
                  }}
                  rows={3}
                />
              </div>
              
              {/* Source field - only show for txt files */}
              {selectedFile && selectedFile.name.toLowerCase().endsWith('.txt') && (
                <div className="form-group">
                  <label htmlFor="source">Source:</label>
                  <input 
                    type="text" 
                    id="source" 
                    value={source}
                    onChange={handleSourceChange}
                    placeholder="Enter source information..."
                    className="form-control"
                    style={{ 
                      color: "#000000",
                      border: "1px solid #e2e8f0",
                      borderRadius: "4px",
                      padding: "8px",
                      width: "100%"
                    }}
                  />
                </div>
              )}
              
              {/* Keywords input hidden but kept in the DOM */}
              <div className="form-group" style={{ display: 'none' }}>
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
              disabled={isProcessing}
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