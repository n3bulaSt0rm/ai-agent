import { useState, useEffect } from 'react';
import '../styles/FilesList.css';
import { toast } from 'react-hot-toast';
import { Link } from 'react-router-dom';
import FileUploader from '../components/FileUploader';
import Pagination from '../components/Pagination';
import LoadingOverlay from '../components/LoadingOverlay';
import '../styles/LoadingOverlay.css';
import filesApi from '../services/api';

// Direct import specific icons with a different method
import CogIcon from '@heroicons/react/24/outline/CogIcon';
import TrashIcon from '@heroicons/react/24/outline/TrashIcon';
import LinkIcon from '@heroicons/react/24/outline/LinkIcon';
import ArrowPathIcon from '@heroicons/react/24/outline/ArrowPathIcon';
import MagnifyingGlassIcon from '@heroicons/react/24/outline/MagnifyingGlassIcon';
import ArrowUpTrayIcon from '@heroicons/react/24/outline/ArrowUpTrayIcon';
import CheckCircleIcon from '@heroicons/react/24/outline/CheckCircleIcon';
import ClockIcon from '@heroicons/react/24/outline/ClockIcon';
import EyeIcon from '@heroicons/react/24/outline/EyeIcon';
import CalendarIcon from '@heroicons/react/24/outline/CalendarIcon';
import PlusIcon from '@heroicons/react/24/outline/PlusIcon';

// Removed all mock data - will now use data from backend API

const ITEMS_PER_PAGE = 6; // Displaying 6 items per page to match the design

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

// Helper function to convert date to YYYY-MM-DD for input elements
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

const FilesList = () => {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showTrash, setShowTrash] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [trashDocuments, setTrashDocuments] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [fileToView, setFileToView] = useState(null);
  const [filterDate, setFilterDate] = useState('');
  const [sortOption, setSortOption] = useState('uploadAt_newest');
  const [trashSortOption, setTrashSortOption] = useState('size_largest');
  const [trashFilterDate, setTrashFilterDate] = useState('');
  
  // Pagination states
  const [currentDocumentsPage, setCurrentDocumentsPage] = useState(1);
  const [currentTrashPage, setCurrentTrashPage] = useState(1);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [totalTrash, setTotalTrash] = useState(0);
  
  // Add function to handle keyword updates
  const [keywordsInput, setKeywordsInput] = useState('');
  
  // New state for process modal
  const [showProcessModal, setShowProcessModal] = useState(false);
  const [documentToProcess, setDocumentToProcess] = useState(null);
  const [pageRanges, setPageRanges] = useState([{ start: 1, end: 1 }]);
  const [pageRangeError, setPageRangeError] = useState("");
  
  const [loadingAction, setLoadingAction] = useState({ isLoading: false, message: '' });
  
  // Add function to handle file_created_at updates
  const [fileCreatedAtInput, setFileCreatedAtInput] = useState('');
  
  // Format the current date as DD/MM/YYYY for the initial display
  useEffect(() => {
    const today = new Date();
    const day = today.getDate().toString().padStart(2, '0');
    const month = (today.getMonth() + 1).toString().padStart(2, '0');
    const year = today.getFullYear();
    
    // Don't set any initial filter, but prepare the date format
    setFilterDate('');
  }, []);
  
  // Fetch file counts when component is first loaded
  useEffect(() => {
    fetchFileCounts();
  }, []);
  
  // Fetch documents from API with pagination, filtering, and sorting
  useEffect(() => {
    fetchDocuments(currentDocumentsPage, filterDate);
    
    // Also fetch file counts for both tabs on initial load
    fetchFileCounts();
  }, [currentDocumentsPage, searchTerm, sortOption, filterDate]);
  
  useEffect(() => {
    if (showTrash) {
      fetchTrashDocuments(currentTrashPage, trashFilterDate, trashSortOption, searchTerm);
    }
  }, [currentTrashPage, showTrash, trashFilterDate, trashSortOption, searchTerm]);
  
  // Fetch documents from API with pagination, filtering, and sorting
  const fetchDocuments = async (page, filterDate = null) => {
    setLoading(true);
    try {
      // Extract sort field and direction if available
      const [field, direction] = sortOption ? sortOption.split('_') : [null, null];
      
      // Use the unified API approach
      const response = await filesApi.getFiles(
        ITEMS_PER_PAGE,
        (page - 1) * ITEMS_PER_PAGE,
        null, // No specific status filter for regular files
        searchTerm, // Search query if any
        filterDate, // Date filter if any
        field,     // Sort field
        direction  // Sort direction
      );
      
      console.log("Fetched documents:", response);
      // Log thêm về status của từng document để debug
      if (response.files && response.files.length > 0) {
        console.log("Document statuses:");
        response.files.forEach(doc => {
          console.log(`Document ID: ${doc.id}, Title: ${doc.title}, Status: ${doc.status}`);
        });
      }
      
      setTotalDocuments(response.total || 0);
      setDocuments(response.files || []);
    } catch (error) {
      console.error('Error fetching documents:', error);
      toast.error('Failed to load documents');
    } finally {
      setLoading(false);
    }
  };
  
  // Fetch trash documents from API with pagination, filtering, and sorting
  const fetchTrashDocuments = async (page, filterDate = null, sortOption = null, searchQuery = null) => {
    setLoading(true);
    try {
      let response;
      
      // Extract filter parameters
      const [field, direction] = sortOption ? sortOption.split('_') : [null, null];
      
      // Call the appropriate API method with all parameters
      response = await filesApi.getTrashFiles(
        ITEMS_PER_PAGE, 
        (page - 1) * ITEMS_PER_PAGE,
        searchQuery || searchTerm, // Pass search term if available
        filterDate, // Pass date filter if provided
        field,      // Sort field
        direction   // Sort direction
      );
      
      setTrashDocuments(response.files);
      setTotalTrash(response.total);
    } catch (error) {
      console.error('Error fetching trash documents:', error);
      toast.error('Failed to load trash documents');
    } finally {
      setLoading(false);
    }
  };
  
  // Add new function to fetch counts for both tabs
  const fetchFileCounts = async () => {
    try {
      // Get file statistics which includes counts for both regular and trash files
      const stats = await filesApi.getFileStats();
      if (stats) {
        // Update counts directly from stats
        setTotalDocuments(stats.total || 0);
        setTotalTrash(stats.trash || 0);
      }
    } catch (error) {
      console.error('Error fetching file counts:', error);
    }
  };
  
  const handleProcess = (doc) => {
    setDocumentToProcess(doc);
    
    // Get existing processed ranges if any
    const existingRanges = [];
    if (doc.pages_processed_range) {
      try {
        const ranges = JSON.parse(doc.pages_processed_range);
        if (Array.isArray(ranges) && ranges.length > 0) {
          existingRanges.push(...ranges); // Keep as strings like "1-5"
        }
      } catch (e) {
        console.error("Error parsing processed ranges:", e);
      }
    }
    
    // If document has no pages yet, set a default range
    if (!doc.pages || doc.pages === 0) {
      setPageRanges([{ start: 1, end: 1 }]);
    } else if (existingRanges.length === 0) {
      // No existing ranges, process the whole document
      setPageRanges([{ start: 1, end: doc.pages }]);
    } else {
      // Find unprocessed ranges
      // Build set of processed pages
      const processedPages = new Set();
      existingRanges.forEach(rangeStr => {
        try {
          const [start, end] = rangeStr.split('-').map(num => parseInt(num, 10));
          for (let page = start; page <= end; page++) {
            processedPages.add(page);
          }
        } catch (e) {
          console.error("Error parsing range:", rangeStr, e);
        }
      });
      
      // Find unprocessed page ranges
      const unprocessedRanges = [];
      let currentStart = null;
      
      for (let page = 1; page <= doc.pages; page++) {
        if (!processedPages.has(page)) {
          if (currentStart === null) {
            currentStart = page;
          }
        } else if (currentStart !== null) {
          // End of a range
          unprocessedRanges.push({ start: currentStart, end: page - 1 });
          currentStart = null;
        }
      }
      
      // Check if we have an open range at the end
      if (currentStart !== null) {
        unprocessedRanges.push({ start: currentStart, end: doc.pages });
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
    setPageRanges([...pageRanges, { start: 1, end: documentToProcess?.pages || 1 }]);
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
    if (documentToProcess?.pages) {
      if (newRanges[index].end > documentToProcess.pages) {
        newRanges[index].end = documentToProcess.pages;
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
      if (documentToProcess.pages_processed_range) {
        try {
          const existingRanges = JSON.parse(documentToProcess.pages_processed_range);
          if (Array.isArray(existingRanges)) {
            for (const newRange of pageRanges) {
              for (const existingRangeStr of existingRanges) {
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
      
      // Convert page ranges to the new string format expected by the backend
      const pageRangesStrings = pageRanges.map(range => `${range.start}-${range.end}`);
      
      // Show loading overlay
      setLoadingAction({ isLoading: true, message: 'Processing document...' });
      setShowProcessModal(false);
      
      // Use the string version of the ranges
      console.log("Sending page ranges:", pageRangesStrings);
      await filesApi.processFile(documentToProcess.id, { page_ranges: pageRangesStrings });
      toast.success(`Processing "${documentToProcess.title}"...`);
      
      fetchDocuments(currentDocumentsPage); // Refresh list after processing starts
    } catch (error) {
      console.error(`Error processing document: ${error}`);
      toast.error('Failed to process document');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  const handleDelete = (doc) => {
    setSelectedDocument(doc);
    setShowDeleteConfirm(true);
  };
  
  const confirmDelete = async () => {
    if (!selectedDocument) return;
    
    setLoadingAction({ isLoading: true, message: 'Moving to trash...' });
    
    try {
      // Đánh dấu tài liệu là đang xóa trước khi gọi API
      const updatedDocuments = documents.map(doc => {
        if (doc.id === selectedDocument.id) {
          return { ...doc, status: 'deleting' };
        }
        return doc;
      });
      setDocuments(updatedDocuments);
      
      // Gửi request API
      const response = await filesApi.deleteFile(selectedDocument.id);
      console.log("Delete API response:", response);
      
      // Không loại bỏ tài liệu khỏi danh sách, để nó hiển thị trạng thái "deleting" 
      // Khi trang được tải lại hoặc API gửi sự kiện cập nhật, tài liệu sẽ tự động chuyển sang trash
      
      // Update file counts
      fetchFileCounts();
      
      // Hide dialog
      setShowDeleteConfirm(false);
      setSelectedDocument(null);
      
      toast.success('Document is being moved to trash');
    } catch (error) {
      console.error('Error deleting document:', error);
      toast.error('Failed to move document to trash');
      
      // Restore original document status if error occurs
      setDocuments(current => 
        current.map(doc => doc.id === selectedDocument.id 
          ? { ...doc, status: selectedDocument.status } 
          : doc
        )
      );
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  const restoreDocument = async (doc) => {
    setLoadingAction({ isLoading: true, message: 'Restoring document...' });
    
    try {
      // Đánh dấu tài liệu là đang khôi phục trước khi gọi API
      const updatedTrashDocuments = trashDocuments.map(d => {
        if (d.id === doc.id) {
          return { ...d, status: 'restoring' };
        }
        return d;
      });
      setTrashDocuments(updatedTrashDocuments);
      
      // Gửi request API
      const response = await filesApi.restoreFile(doc.id);
      console.log("Restore API response:", response);
      
      // Không loại bỏ tài liệu khỏi danh sách trash, để nó hiển thị trạng thái "restoring"
      // Khi trang được tải lại hoặc API gửi sự kiện cập nhật, tài liệu sẽ tự động chuyển sang all documents
      
      // Update file counts
      fetchFileCounts();
      
      toast.success('Document is being restored');
    } catch (error) {
      console.error('Error restoring document:', error);
      toast.error('Failed to restore document');
      
      // Restore original document status if error occurs
      setTrashDocuments(current => 
        current.map(d => d.id === doc.id 
          ? { ...d, status: doc.status } 
          : d
        )
      );
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  const copyLink = (doc) => {
    navigator.clipboard.writeText(doc.link || doc.view_url);
    toast.success('Link copied to clipboard');
  };
  
  const handleFileSelected = (file) => {
    // Memastikan keywords dipertahankan dalam objek file
    if (file) {
      console.log('File selected with keywords:', file.keywords);
    }
    setSelectedFile(file);
  };
  
  // Handle file upload
  const handleUpload = async () => {
    if (!selectedFile) {
      toast.error('Please select a file to upload');
      return;
    }
    
    setLoadingAction({ isLoading: true, message: 'Uploading file, please wait...' });
    
    try {
      // Call API to upload file
      const uploadedFile = await filesApi.uploadFile(selectedFile, selectedFile.description, selectedFile.fileCreatedAt, selectedFile.keywords);
      
      // Add file to documents list
      setDocuments([uploadedFile, ...documents]);
      
      // Reset selected file
      setSelectedFile(null);
      
      // Hide modal
      setShowUploadModal(false);
      
      // Update file counts
      fetchFileCounts();
      
      // Show success message
      toast.success('File uploaded successfully');
    } catch (error) {
      console.error('Error uploading file:', error);
      toast.error('Failed to upload file');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  const getStatusBadge = (status) => {
    switch(status) {
      case 'processed':
        return (
          <span className="status-badge processed">
            <CheckCircleIcon className="w-4 h-4 mr-1" />
            Processed
          </span>
        );
      case 'processing':
        return (
          <span className="status-badge processing">
            <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin" />
            Processing
          </span>
        );
      case 'preparing':
        return (
          <span className="status-badge preparing">
            <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin" />
            Preparing
          </span>
        );
      case 'deleting':
        return (
          <span className="status-badge deleting">
            <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin" />
            Deleting
          </span>
        );
      case 'restoring':
        return (
          <span className="status-badge restoring">
            <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin" />
            Restoring
          </span>
        );
      case 'pending_upload':
      case 'pending':
        return (
          <span className="status-badge pending">
            <ClockIcon className="w-4 h-4 mr-1" />
            Pending
          </span>
        );
      default:
        return (
          <span className="status-badge">
            Unknown
          </span>
        );
    }
  };
  
  // Handle page change for documents list
  const handleDocumentsPageChange = (page) => {
    setCurrentDocumentsPage(page);
  };
  
  // Handle page change for trash list
  const handleTrashPageChange = (page) => {
    setCurrentTrashPage(page);
  };
  
  // Toggle between documents and trash
  const handleToggleTrash = (showTrashView) => {
    console.log("Toggling trash view:", showTrashView);
    setShowTrash(showTrashView);
    
    // Reset to page 1 when switching views
    if (showTrashView) {
      console.log("Fetching trash documents on toggle");
      setCurrentTrashPage(1);
      // Only fetch trash content if needed, but don't reset the count
      if (trashDocuments.length === 0) {
        setTimeout(() => {
          fetchTrashDocuments(1, trashFilterDate, trashSortOption);
        }, 0);
      }
    } else {
      setCurrentDocumentsPage(1);
      // Refetch documents only if needed
      if (documents.length === 0) {
        fetchDocuments(1, filterDate);
      }
    }
  };
  
  // Calculate total pages
  const totalDocumentsPages = Math.ceil(totalDocuments / ITEMS_PER_PAGE);
  const totalTrashPages = Math.ceil(totalTrash / ITEMS_PER_PAGE);
  
  // Handle search when Enter key is pressed
  const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter') {
      setSearchTerm(searchQuery);
      
      // Reset to page 1 when searching
      if (showTrash) {
        setCurrentTrashPage(1);
        // Trigger search in trash files
        fetchTrashDocuments(1, trashFilterDate, trashSortOption, searchQuery);
      } else {
        setCurrentDocumentsPage(1);
        // Search in regular files (handled by useEffect)
      }
    }
  };
  
  const handleViewDetail = (doc) => {
    setFileToView({
      ...doc,
      keywords: doc.keywords || [] // Get keywords directly
    });
    setKeywordsInput(doc.keywords ? doc.keywords.join(', ') : '');
    setFileCreatedAtInput(doc.fileCreatedAt || '');
    setShowDetailModal(true);
  };
  
  // Handle sort change
  const handleSortChange = (e) => {
    const newSortOption = e.target.value;
    setSortOption(newSortOption);
    // Reset to page 1 when changing sort
    setCurrentDocumentsPage(1);
  };
  
  // Update handleDateChange function to use the filter API
  const handleDateChange = async (e) => {
    const selectedDate = e.target.value;
    
    // If empty, clear the filter
    if (!selectedDate) {
      setFilterDate('');
      fetchDocuments(1, '');
      setCurrentDocumentsPage(1);
      toast.success('Showing all documents');
      return;
    }
    
    // Convert YYYY-MM-DD to DD/MM/YYYY for display
    const [year, month, day] = selectedDate.split('-');
    const formattedDate = `${day}/${month}/${year}`;
    
    // Update the display element to show the selected date
    const dateLabel = document.querySelector('.date-display');
    if (dateLabel) {
      dateLabel.textContent = formattedDate;
    }
    
    setFilterDate(formattedDate);
    
    // Send the date in YYYY-MM-DD format to the API
    try {
      await fetchDocuments(1, selectedDate);
      
      // Reset to page 1 when applying a new filter
      setCurrentDocumentsPage(1);
      
      // Notify user about filter
      toast.success(`Filtering documents by date: ${formattedDate}`);
    } catch (error) {
      console.error('Error filtering by date:', error);
      toast.error('Failed to filter documents');
    }
  };
  
  const handleTrashSortChange = (e) => {
    const newTrashSortOption = e.target.value;
    setTrashSortOption(newTrashSortOption);
    // Reset to page 1 when changing sort
    setCurrentTrashPage(1);
  };
  
  const handleTrashDateChange = (e) => {
    const selectedTrashDate = e.target.value;
    
    // If empty, clear the filter
    if (!selectedTrashDate) {
      setTrashFilterDate('');
      fetchTrashDocuments(1);
      setCurrentTrashPage(1);
      toast.success('Showing all documents');
      return;
    }
    
    // Convert YYYY-MM-DD to DD/MM/YYYY for display
    const [year, month, day] = selectedTrashDate.split('-');
    const formattedTrashDate = `${day}/${month}/${year}`;
    
    // Update the display element to show the selected date
    const trashDateLabel = document.querySelector('.date-display');
    if (trashDateLabel) {
      trashDateLabel.textContent = formattedTrashDate;
    }
    
    setTrashFilterDate(formattedTrashDate);
    
    // Send the date in YYYY-MM-DD format to the API
    try {
      fetchTrashDocuments(1, selectedTrashDate);
      
      // Reset to page 1 when applying a new filter
      setCurrentTrashPage(1);
      
      // Notify user about filter
      toast.success(`Filtering documents by date: ${formattedTrashDate}`);
    } catch (error) {
      console.error('Error filtering by date:', error);
      toast.error('Failed to filter documents');
    }
  };
  
  // Add function to handle keyword updates
  const handleKeywordsUpdate = async () => {
    if (!fileToView) return;
    
    try {
      // Show loading overlay
      setLoadingAction({ isLoading: true, message: 'Updating keywords...' });
      
      // Call API to update keywords with the raw input string
      await filesApi.updateKeywords(fileToView.id, keywordsInput);
      
      // Update local state - for display purposes, we still parse to array
      const keywordArray = keywordsInput.split(',')
        .map(k => k.trim())
        .filter(k => k);
      
      setFileToView({
        ...fileToView,
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
  
  // Add function to handle file created date update
  const handleFileCreatedAtUpdate = async () => {
    if (!fileToView) return;
    
    try {
      // Show loading overlay
      setLoadingAction({ isLoading: true, message: 'Updating file date...' });
      
      // Call API to update file created date
      await filesApi.updateFileCreatedAt(fileToView.id, fileCreatedAtInput);
      
      // Update local state
      setFileToView({
        ...fileToView,
        fileCreatedAt: fileCreatedAtInput
      });
      
      toast.success('File creation date updated successfully');
      
    } catch (error) {
      console.error('Error updating file creation date:', error);
      toast.error('Failed to update file creation date');
    } finally {
      setLoadingAction({ isLoading: false, message: '' });
    }
  };
  
  return (
    <div className="page-container files-list">
      {/* Loading overlay */}
      <LoadingOverlay 
        isVisible={loadingAction.isLoading}
        message={loadingAction.message}
      />
      
      <div className="page-header">
        <div>
          <h1>Documents</h1>
          <p>Manage your uploaded documents</p>
        </div>
        <div className="header-actions" style={{ 
          display: "flex", 
          alignItems: "center", 
          gap: "10px",
          height: "40px" // Fixed container height
        }}>
          <div className="search-box" style={{ 
            width: "360px",
            position: "relative",
            height: "40px", // Exact same height as button
            margin: 0,
            padding: 0,
            boxSizing: "border-box"
          }}>
            <div style={{ 
              position: "absolute",
              left: "10px",
              top: "50%",
              transform: "translateY(-50%)",
              zIndex: 2,
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}>
              <MagnifyingGlassIcon className="search-icon" style={{ width: "20px", height: "20px" }} />
            </div>
            <input 
              type="text" 
              placeholder="Search by document name..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              style={{ 
                position: "absolute",
                left: 0,
                top: 0,
                width: "100%",
                height: "100%",
                paddingLeft: "40px", // Make room for the icon
                paddingRight: searchTerm ? "40px" : "10px", // Extra padding when clear button is visible
                margin: 0,
                boxSizing: "border-box",
                color: "#000000", /* Ensure text is visible */
                fontSize: "14px",
                fontWeight: "normal",
                background: "white",
                border: "none",
                outline: "none",
                zIndex: 1
              }}
            />
            {searchTerm && (
              <button 
                onClick={() => {
                  setSearchQuery('');
                  setSearchTerm('');
                  if (showTrash) {
                    fetchTrashDocuments(1, trashFilterDate, trashSortOption, '');
                    setCurrentTrashPage(1);
                  } else {
                    fetchDocuments(1, filterDate);
                    setCurrentDocumentsPage(1);
                  }
                  toast.success('Search cleared');
                }}
                style={{
                  position: "absolute",
                  right: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  zIndex: 2,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#64748b",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "24px",
                  height: "24px",
                  padding: 0
                }}
                title="Clear search"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" style={{width: "16px", height: "16px"}}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
          <button 
            className="btn-primary" 
            onClick={() => setShowUploadModal(true)}
            style={{ height: "40px", boxSizing: "border-box" }}
          >
            <ArrowUpTrayIcon className="w-5 h-5 mr-2" />
            Upload
          </button>
        </div>
      </div>
      
      <div className="documents-actions">
        <div className="documents-tabs">
          <button 
            className={`tab-btn ${!showTrash ? 'active' : ''}`}
            onClick={() => handleToggleTrash(false)}
          >
            All Documents
            <span className="badge">{totalDocuments}</span>
          </button>
          <button 
            className={`tab-btn ${showTrash ? 'active' : ''}`}
            onClick={() => handleToggleTrash(true)}
          >
            Trash
            <span className="badge">{totalTrash}</span>
          </button>
        </div>
        
        {!showTrash ? (
          <div className="filter-controls">
            <select 
              className="select-control"
              value={sortOption}
              onChange={handleSortChange}
            >
              <option value="size_largest">Size (largest)</option>
              <option value="size_smallest">Size (smallest)</option>
              <option value="uploadAt_newest">Upload At (newest)</option>
              <option value="uploadAt_oldest">Upload At (oldest)</option>
              <option value="updatedAt_newest">Updated At (newest)</option>
              <option value="updatedAt_oldest">Updated At (oldest)</option>
              <option value="fileCreatedAt_newest">File Created (newest)</option>
              <option value="fileCreatedAt_oldest">File Created (oldest)</option>
            </select>
            <div className="date-field">
              <input 
                type="date" 
                id="datePicker"
                value={filterDate ? toInputDateFormat(filterDate) : ''}
                onChange={handleDateChange}
              />
              <label htmlFor="datePicker" className="date-label">
                <span className="date-display">{filterDate || 'mm/dd/yyyy'}</span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M8 7V3M16 7V3M7 11H17M5 21H19C20.1046 21 21 20.1046 21 19V7C21 5.89543 20.1046 5 19 5H5C3.89543 5 3 5.89543 3 7V19C3 20.1046 3.89543 21 5 21Z" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </label>
            </div>
          </div>
        ) : (
          <div className="filter-controls">
            <select 
              className="select-control"
              value={trashSortOption}
              onChange={handleTrashSortChange}
            >
              <option value="size_largest">Size (largest)</option>
              <option value="size_smallest">Size (smallest)</option>
              <option value="deletedDate_newest">Deleted Date (newest)</option>
              <option value="deletedDate_oldest">Deleted Date (oldest)</option>
              <option value="uploadAt_newest">Upload At (newest)</option>
              <option value="uploadAt_oldest">Upload At (oldest)</option>
            </select>
            <div className="date-field">
              <input 
                type="date" 
                id="trashDatePicker"
                value={trashFilterDate ? toInputDateFormat(trashFilterDate) : ''}
                onChange={handleTrashDateChange}
              />
              <label htmlFor="trashDatePicker" className="date-label">
                <span className="date-display">{trashFilterDate || 'mm/dd/yyyy'}</span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M8 7V3M16 7V3M7 11H17M5 21H19C20.1046 21 21 20.1046 21 19V7C21 5.89543 20.1046 5 19 5H5C3.89543 5 3 5.89543 3 7V19C3 20.1046 3.89543 21 5 21Z" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </label>
            </div>
          </div>
        )}
      </div>
      
      {loading ? (
        <div className="card">
          <div className="empty-state">
            <div className="loading-spinner">
              <ArrowPathIcon className="w-8 h-8 animate-spin" />
            </div>
            <p>Loading documents...</p>
          </div>
        </div>
      ) : !showTrash ? (
        documents.length > 0 ? (
          <>
            <div className="card data-card">
              <div className="table-container">
                <table className="documents-table">
                  <thead>
                    <tr>
                      <th width="40%" className="text-center">Document Name</th>
                      <th width="10%" className="text-center">Size</th>
                      <th width="10%" className="text-center">Pages</th>
                      <th width="15%" className="text-center">Status</th>
                      <th width="15%" className="text-center">Upload At</th>
                      <th width="10%" className="text-center">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map(doc => (
                      <tr key={doc.id}>
                        <td className="document-cell">
                          <div className={`document-type ${doc.type}`}></div>
                          <div className="document-info">
                            <span className="document-title">{doc.title}</span>
                            <span className="document-meta">Uploaded by {doc.uploadedBy}</span>
                          </div>
                        </td>
                        <td className="text-center">{doc.size}</td>
                        <td className="text-center">{doc.pages}</td>
                        <td className="text-center">
                          <div className="flex justify-center">
                            {getStatusBadge(doc.status)}
                          </div>
                        </td>
                        <td className="text-center">{formatDate(doc.uploadAt)}</td>
                        <td>
                          <div className="action-buttons">
                            <button 
                              className="action-icon view-btn" 
                              onClick={() => handleViewDetail(doc)}
                              title="View details"
                              style={{ 
                                backgroundColor: '#f1f5f9',
                                border: 'none', 
                                borderRadius: '4px',
                                padding: '6px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                width: '32px',
                                height: '32px',
                                color: '#64748b',
                                cursor: 'pointer'
                              }}
                            >
                              <svg 
                                xmlns="http://www.w3.org/2000/svg" 
                                fill="none" 
                                viewBox="0 0 24 24" 
                                strokeWidth={1.5} 
                                stroke="currentColor" 
                                style={{
                                  width: '20px',
                                  height: '20px',
                                  minWidth: '20px',
                                  minHeight: '20px'
                                }}
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
                                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                              </svg>
                            </button>
                            {doc.status === 'pending_upload' || doc.status === 'pending' ? (
                              <button 
                                className="action-icon process-btn" 
                                onClick={() => handleProcess(doc)}
                                title="Process document"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
                                </svg>
                              </button>
                            ) : null}
                            <button 
                              className="action-icon link-btn" 
                              onClick={() => copyLink(doc)}
                              title="Copy link"
                              style={{ 
                                backgroundColor: '#f1f5f9',
                                border: 'none', 
                                borderRadius: '4px',
                                padding: '6px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                width: '32px',
                                height: '32px',
                                color: '#64748b',
                                cursor: 'pointer'
                              }}
                            >
                              <svg 
                                xmlns="http://www.w3.org/2000/svg" 
                                fill="none" 
                                viewBox="0 0 24 24" 
                                strokeWidth={1.5} 
                                stroke="currentColor" 
                                style={{
                                  width: '20px',
                                  height: '20px',
                                  minWidth: '20px',
                                  minHeight: '20px'
                                }}
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
                              </svg>
                            </button>
                            {doc.status !== 'processing' && doc.status !== 'preparing' && doc.status !== 'deleting' && doc.status !== 'restoring' && (
                              <button 
                                className="action-icon delete-btn" 
                                onClick={() => handleDelete(doc)}
                                title="Delete document"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                                </svg>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {/* Pagination for documents */}
            <Pagination 
              key={`documents-pagination-${currentDocumentsPage}`}
              currentPage={currentDocumentsPage} 
              totalPages={totalDocumentsPages} 
              onPageChange={handleDocumentsPageChange} 
            />
          </>
        ) : (
          <div className="card">
            <div className="empty-state">
              <div className="empty-icon"></div>
              <h3>No documents found</h3>
              {searchQuery ? (
                <p>No documents match your search. Try using different keywords.</p>
              ) : (
                <>
                  <p>Upload your first document to get started</p>
                  <button 
                    className="btn-primary"
                    onClick={() => setShowUploadModal(true)}
                  >
                    <ArrowUpTrayIcon className="w-5 h-5 mr-2" />
                    Upload Document
                  </button>
                </>
              )}
            </div>
          </div>
        )
      ) : (
        <>
          <div className="card data-card">
            <div className="table-container">
              <table className="documents-table">
                <thead>
                  <tr>
                    <th width="40%" className="text-center">Document Name</th>
                    <th className="text-center">Size</th>
                    <th className="text-center">Pages</th>
                    <th className="text-center">Deleted Date</th>
                    <th className="text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {trashDocuments.length > 0 ? (
                    trashDocuments.map(doc => (
                      <tr key={doc.id} className="deleted-row">
                        <td className="document-cell">
                          <div className={`document-type ${doc.type}`}></div>
                          <div className="document-info">
                            <span className="document-title">{doc.title}</span>
                            <span className="document-meta">Deleted by {doc.deletedBy}</span>
                          </div>
                        </td>
                        <td className="text-center">{doc.size}</td>
                        <td className="text-center">{doc.pages}</td>
                        <td className="text-center">{formatDate(doc.deletedDate)}</td>
                        <td>
                          <div className="action-buttons">
                            <button 
                              className="action-icon" 
                              title="Restore document"
                              onClick={() => restoreDocument(doc)}
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                              </svg>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="5" className="text-center py-4">
                        <p>No documents in trash</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
          {/* Pagination for trash */}
          {trashDocuments.length > 0 && (
            <Pagination 
              key={`trash-pagination-${currentTrashPage}`}
              currentPage={currentTrashPage} 
              totalPages={totalTrashPages} 
              onPageChange={handleTrashPageChange} 
            />
          )}
        </>
      )}
      
      {/* Upload Modal */}
      {showUploadModal && (
        <div className="modal-overlay" onClick={() => setShowUploadModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Upload New Document</h2>
              <button className="close-btn" onClick={() => setShowUploadModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <FileUploader 
                onFileSelected={handleFileSelected}
                acceptedFormats={['.pdf', '.docx', '.doc']}
                maxSize={10}
              />
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowUploadModal(false)}>Cancel</button>
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
      
      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && selectedDocument && (
        <div className="modal-overlay" onClick={() => setShowDeleteConfirm(false)}>
          <div className="modal-content confirm-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete Document</h2>
              <button className="close-btn" onClick={() => setShowDeleteConfirm(false)}>×</button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to move "{selectedDocument.title}" to trash?</p>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowDeleteConfirm(false)}>Cancel</button>
              <button className="btn-danger" onClick={confirmDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
      
      {/* File Detail Modal */}
      {showDetailModal && fileToView && (
        <div className="modal-overlay">
          <div className="modal-container">
            <div className="modal-header">
              <h2>Document Details</h2>
              <button className="close-btn" onClick={() => setShowDetailModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="document-icon-container">
                <div className={`document-type-large ${fileToView.type}`}></div>
                <h3 className="document-title-large">{fileToView.title}</h3>
              </div>
              
              <div className="detail-tabs">
                <div className="detail-tab active">Details</div>
              </div>
              
              <div className="detail-grid">
                <div className="detail-section">
                  <h4 className="detail-section-title">General Information</h4>
                  <div className="detail-row">
                    <span className="detail-label">Size:</span>
                    <span className="detail-value">{fileToView.size}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Pages:</span>
                    <span className="detail-value">{fileToView.pages}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Status:</span>
                    <span className="detail-value">{getStatusBadge(fileToView.status)}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Upload Date:</span>
                    <span className="detail-value">{formatDate(fileToView.uploadAt)}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Created Date:</span>
                    <span className="detail-value">{formatDate(fileToView.fileCreatedAt)}</span>
                  </div>
                </div>
                
                {fileToView.description && (
                  <div className="detail-section">
                    <h4 className="detail-section-title">Description</h4>
                    <div className="detail-description">{fileToView.description}</div>
                  </div>
                )}
                
                {/* Keywords section - hidden but logic maintained */}
                <div className="detail-section keywords-section" style={{ display: 'none' }}>
                  <h4 className="detail-section-title">Keywords</h4>
                  <div className="keyword-tags">
                    {fileToView.keywords && fileToView.keywords.length > 0 ? (
                      fileToView.keywords.map((keyword, index) => (
                        <span key={index} className="keyword-tag">{keyword}</span>
                      ))
                    ) : (
                      <span className="no-keywords">No keywords</span>
                    )}
                  </div>
                
                  <div className="keyword-edit-section">
                    <label htmlFor="keywords">Edit Keywords (comma separated):</label>
                    <div className="keyword-input-group">
                      <input 
                        type="text" 
                        id="keywords" 
                        defaultValue={fileToView.keywords ? fileToView.keywords.join(', ') : ''}
                        onChange={(e) => setKeywordsInput(e.target.value)}
                        placeholder="Enter keywords separated by commas"
                        className="form-control"
                      />
                      <button 
                        className="btn-primary save-keywords"
                        onClick={handleKeywordsUpdate}
                      >
                        Update Keywords
                      </button>
                    </div>
                  </div>
                </div>
                
                <div className="detail-section file-date-section">
                  <h4 className="detail-section-title">Edit Created Date</h4>
                  <div className="date-edit-section">
                    <label htmlFor="fileCreatedAt">Update File Creation Date:</label>
                    <div className="date-input-group">
                      <input 
                        type="date" 
                        id="fileCreatedAt" 
                        value={toInputDateFormat(fileCreatedAtInput)}
                        onChange={(e) => setFileCreatedAtInput(e.target.value)}
                        className="form-control"
                      />
                      <button 
                        className="btn-primary save-date"
                        onClick={handleFileCreatedAtUpdate}
                      >
                        Update Date
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="detail-actions">
                <a 
                  href={fileToView.view_url} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="btn-secondary"
                >
                  <EyeIcon className="w-5 h-5 mr-2" />
                  View Document
                </a>
                {fileToView.status === 'pending_upload' || fileToView.status === 'pending' ? (
                  <button 
                    className="btn-primary"
                    onClick={() => {
                      handleProcess(fileToView);
                      setShowDetailModal(false);
                    }}
                  >
                    <ArrowPathIcon className="w-5 h-5 mr-2" />
                    Process Document
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Process Page Range Modal */}
      {showProcessModal && documentToProcess && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>Process Document</h2>
              <button className="close-button" onClick={() => setShowProcessModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="document-process-info">
                <h3>{documentToProcess.title}</h3>
                <p className="document-pages-info">
                  Document has <strong>{documentToProcess.pages || "unknown"}</strong> pages
                </p>
              </div>
              
              <div className="process-instruction">
                <p>Select the page ranges you want to process:</p>
              </div>
              
              {pageRangeError && (
                <div className="error-message">{pageRangeError}</div>
              )}
              
              {pageRanges.length > 0 ? (
                pageRanges.map((range, index) => (
                  <div className="page-range-row" key={index}>
                    <div className="range-number">{index + 1}</div>
                    <div className="range-inputs">
                      <label>
                        <span>Start Page:</span>
                        <input 
                          type="number" 
                          min="1" 
                          max={documentToProcess.pages || 1}
                          value={range.start}
                          onChange={(e) => handlePageRangeChange(index, 'start', e.target.value)}
                        />
                      </label>
                      <label>
                        <span>End Page:</span>
                        <input 
                          type="number" 
                          min={range.start} 
                          max={documentToProcess.pages || 1}
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
                  className="btn-add-range" 
                  onClick={handleAddPageRange}
                  disabled={pageRanges.length === 0}
                >
                  <PlusIcon className="w-5 h-5 mr-1" />
                  Add Page Range
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
                className="btn-primary btn-process" 
                onClick={handleConfirmProcess}
                disabled={pageRanges.length === 0 || pageRangeError}
              >
                <ArrowPathIcon className="w-5 h-5 mr-1" />
                Process Document
              </button>
            </div>
          </div>
        </div>
      )}
      
      <style jsx>{`
        .filter-controls {
          display: flex;
          align-items: center;
          gap: 12px;
          padding-right: 8px;
          height: 38px; /* Ensure consistent container height */
        }
        
        .select-control {
          padding: 0 12px;
          border: 1px solid #e2e8f0;
          border-radius: 4px;
          font-size: 14px;
          background-color: white;
          color: #64748b;
          height: 38px; /* Consistent height */
          width: 230px;
          font-family: 'Inter', sans-serif;
          box-sizing: border-box;
          margin: 0; /* Remove any margins */
        }
        
        .date-field {
          position: relative;
          width: 200px;
          height: 38px; /* Consistent height */
          box-sizing: border-box;
          margin: 0; /* Remove any margins */
          display: flex;
          align-items: center;
        }
        
        .date-field input[type="date"] {
          width: 100%;
          height: 100%;
          padding: 0 12px;
          border: 1px solid #e2e8f0;
          border-radius: 4px;
          font-size: 14px;
          background-color: white;
          color: #64748b;
          font-family: 'Inter', sans-serif;
          box-sizing: border-box;
          z-index: 1;
          position: relative;
          opacity: 0; /* Hide the default date input */
          cursor: pointer;
        }
        
        .date-label {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 38px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 12px;
          border: 1px solid #e2e8f0;
          border-radius: 4px;
          background-color: white;
          pointer-events: none;
          box-sizing: border-box;
        }
        
        .date-display {
          font-size: 14px;
          color: #64748b;
        }
        
        .date-label svg {
          min-width: 20px;
          min-height: 20px;
        }
        
        /* Detail modal styling */
        .detail-modal {
          max-width: 600px;
          width: 100%;
        }
        
        .detail-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 16px;
        }
        
        .detail-item {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        
        .detail-label {
          font-weight: 600;
          color: #64748b;
          font-size: 14px;
        }
        
        .detail-value {
          font-size: 16px;
        }
        
        .detail-value.link {
          display: flex;
          align-items: center;
          gap: 8px;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        
        .detail-value.link a {
          color: #3b82f6;
          text-decoration: none;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        
        .copy-link-btn {
          background: #f1f5f9;
          border: none;
          border-radius: 4px;
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
};

export default FilesList; 