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
  uploadFile: async (file, description, fileCreatedAt = null) => {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('description', description || '');
      
      if (fileCreatedAt) {
        formData.append('file_created_at', fileCreatedAt);
      }
      
      const response = await apiClient.post('/files/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      return response.data;
    } catch (error) {
      console.error('Error uploading file:', error);
      throw error;
    }
  },
  
  // Process a file
  processFile: async (fileId) => {
    try {
      const response = await apiClient.post(`/files/${fileId}/process`);
      return response.data;
    } catch (error) {
      console.error(`Error processing file ${fileId}:`, error);
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
  }
};

export default filesApi; 