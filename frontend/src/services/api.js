import axios from 'axios';

// Base API URL
const API_URL = 'http://localhost:8000/api';

// Create axios instance
const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  }
});

// API service for Files management
const filesApi = {
  // Get all files with pagination and optional filters
  getFiles: async (limit = 6, offset = 0, status = null, query = null, date = null, sort_by = null, sort_order = null) => {
    try {
      let url = `/files/?limit=${limit}&offset=${offset}`;
      
      // Add optional filters
      if (status) {
        url += `&status=${status}`;
      }
      if (query) {
        url += `&query=${encodeURIComponent(query)}`;
      }
      if (date) {
        url += `&date=${date}`;
      }
      if (sort_by) {
        url += `&sort_by=${sort_by}`;
      }
      if (sort_order) {
        url += `&sort_order=${sort_order}`;
      }
      
      const response = await apiClient.get(url);
      return response.data;
    } catch (error) {
      console.error('Error fetching files:', error);
      throw error;
    }
  },
  
  // Get a single file by ID
  getFile: async (fileId) => {
    try {
      const response = await apiClient.get(`/files/${fileId}`);
      return response.data;
    } catch (error) {
      console.error(`Error fetching file ${fileId}:`, error);
      throw error;
    }
  },
  
  // Upload a new file
  uploadFile: async (file, description, fileCreatedAt = null, keywords = null) => {
    try {
      // Verify that file is valid before proceeding
      if (!file || !(file instanceof File)) {
        console.error('Invalid file object:', file);
        throw new Error('Invalid file object provided for upload');
      }
      
      console.log('API uploadFile - Starting upload for file:', file.name, 'size:', file.size);
      
      const formData = new FormData();
      formData.append('file', file);
      formData.append('description', description || '');
      
      if (fileCreatedAt) {
        formData.append('file_created_at', fileCreatedAt);
      }
      
      // Pastikan keywords selalu dikirim, bahkan jika kosong
      // Dan pastikan nilai yang kita teruskan adalah string
      const keywordsStr = keywords ? keywords.toString() : '';
      console.log('API uploadFile - Adding keywords to form:', keywordsStr);
      formData.append('keywords', keywordsStr);
      
      // Log semua nilai form untuk debugging
      console.log('API uploadFile - FormData contents:');
      for (let pair of formData.entries()) {
        console.log(pair[0] + ': ' + (pair[0] === 'file' ? `[File: ${pair[1].name}, size: ${pair[1].size}, type: ${pair[1].type}]` : pair[1]));
      }
      
      const response = await apiClient.post('/files/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      console.log('API uploadFile - Response received:', response.status);
      console.log('API uploadFile - Response keywords:', response.data.keywords);
      return response.data;
    } catch (error) {
      console.error('Error uploading file:', error);
      if (error.response) {
        console.error('Server response:', error.response.status, error.response.data);
      }
      throw error;
    }
  },
  
  // Process a file
  processFile: async (fileId, options = null) => {
    try {
      let response;
      if (options && options.page_ranges) {
        // Log và gửi options giống hệt như vậy
        console.log("Sending process file request with options:", JSON.stringify(options));
        response = await apiClient.post(`/files/${fileId}/process`, options);
      } else {
        // Backward compatibility for calls without page ranges
        response = await apiClient.post(`/files/${fileId}/process`);
      }
      return response.data;
    } catch (error) {
      console.error(`Error processing file ${fileId}:`, error);
      if (error.response) {
        console.error('Error response data:', error.response.data);
      }
      throw error;
    }
  },
  
  // Update file metadata
  updateFile: async (fileId, data) => {
    try {
      const response = await apiClient.put(`/files/update/${fileId}`, data);
      return response.data;
    } catch (error) {
      console.error(`Error updating file ${fileId}:`, error);
      throw error;
    }
  },
  
  // Update file keywords
  updateKeywords: async (fileId, keywords) => {
    try {
      console.log("Updating keywords for file", fileId, "with:", keywords);
      
      // Send keywords as they are without conversion
      const response = await apiClient.put(`/files/update/${fileId}`, {
        keywords: keywords
      });
      return response.data;
    } catch (error) {
      console.error(`Error updating keywords for file ${fileId}:`, error);
      throw error;
    }
  },
  
  // Delete a file (move to trash)
  deleteFile: async (fileId) => {
    try {
      const response = await apiClient.delete(`/files/${fileId}`);
      return response.data;
    } catch (error) {
      console.error(`Error deleting file ${fileId}:`, error);
      throw error;
    }
  },
  
  // Restore a file from trash
  restoreFile: async (fileId) => {
    try {
      const response = await apiClient.post(`/files/${fileId}/restore`);
      return response.data;
    } catch (error) {
      console.error(`Error restoring file ${fileId}:`, error);
      throw error;
    }
  },
  
  // Get files in trash - Uses unified endpoint with status=deleted
  getTrashFiles: async (limit = 6, offset = 0, query = null, date = null, sort_by = null, sort_order = null) => {
    try {
      console.log("Fetching trash files with params:", { limit, offset, query, date, sort_by, sort_order });
      
      let url = `/files?limit=${limit}&offset=${offset}&status=deleted`;
      
      // Add optional filters
      if (query) {
        url += `&query=${encodeURIComponent(query)}`;
      }
      if (date) {
        url += `&date=${date}`;
      }
      if (sort_by) {
        url += `&sort_by=${sort_by}`;
      }
      if (sort_order) {
        url += `&sort_order=${sort_order}`;
      }
      
      const response = await apiClient.get(url);
      console.log("Trash files response:", response.data);
      return response.data;
    } catch (error) {
      console.error('Error fetching trash files:', error);
      console.error('Error details:', error.response?.data || 'No response data');
      throw error;
    }
  },
  
  // Search files - Use unified endpoint with query parameter
  searchFiles: async (query, limit = 6, offset = 0, status = null) => {
    try {
      console.log("Searching files with params:", { query, limit, offset, status });
      return filesApi.getFiles(limit, offset, status, query);
    } catch (error) {
      console.error('Error searching files:', error);
      throw error;
    }
  },
  
  // Get file statistics
  getFileStats: async () => {
    try {
      console.log("Fetching stats from:", `${API_URL}/files/stats`);
      const response = await apiClient.get('/files/stats');
      console.log("Stats API response:", response.data);
      return response.data;
    } catch (error) {
      console.error('Error fetching file statistics:', error);
      console.error('Error details:', error.response?.data || 'No response data');
      // Return default empty stats to prevent UI errors
      return {
        total: 0,
        pending: 0,
        processing: 0,
        processed: 0,
        trash: 0
      };
    }
  },
  
  // Filter files by date - Use unified endpoint with date parameter
  filterFilesByDate: async (date, limit = 6, offset = 0, status = null) => {
    try {
      return this.getFiles(limit, offset, status, null, date);
    } catch (error) {
      console.error(`Error filtering files by date ${date}:`, error);
      throw error;
    }
  },
  
  // Sort files - Use unified endpoint with sort_by and sort_order parameters
  sortFiles: async (sortBy, sortOrder = 'desc', limit = 6, offset = 0, status = null) => {
    try {
      return this.getFiles(limit, offset, status, null, null, sortBy, sortOrder);
    } catch (error) {
      console.error(`Error sorting files by ${sortBy}:`, error);
      throw error;
    }
  },
  
  // Add updateFileCreatedAt method to the API service
  updateFileCreatedAt: async (fileId, fileCreatedAt) => {
    try {
      const response = await apiClient.put(`/files/update/${fileId}`, {
        file_created_at: fileCreatedAt
      });
      return response.data;
    } catch (error) {
      throw error;
    }
  },
  
  // Add updateFileDescription method to the API service
  updateFileDescription: async (fileId, description) => {
    try {
      const response = await apiClient.put(`/files/update/${fileId}`, {
        description: description
      });
      return response.data;
    } catch (error) {
      throw error;
    }
  },

  // Get processing service health status
  getProcessingServiceHealth: async () => {
    try {
      // Call directly to the processing service
      const processingServiceUrl = "http://localhost:8081/health";
      console.log("Checking processing service health at:", processingServiceUrl);
      
      const response = await axios.get(processingServiceUrl, { timeout: 5000 });
      console.log("Health check response:", response.data);
      
      // Process the JSON response from the health endpoint
      if (response.status === 200 && response.data) {
        return {
          status: response.data.status || "online",
          message: response.data.message || "Service is running normally",
          timestamp: response.data.timestamp || new Date().toISOString()
        };
      } else {
        return {
          status: "degraded",
          message: `Unexpected response: ${response.status}`,
          timestamp: new Date().toISOString()
        };
      }
    } catch (error) {
      console.error('Error fetching health status:', error);
      console.error('Error details:', error.response?.data || 'No response data');
      return {
        status: "offline",
        message: error.message || "Failed to connect to processing service",
        timestamp: new Date().toISOString()
      };
    }
  }
};

export default filesApi; 