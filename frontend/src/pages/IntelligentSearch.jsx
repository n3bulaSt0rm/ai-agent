import { useState, useRef, useEffect } from 'react';
import { searchApi } from '../services/api';
import '../styles/IntelligentSearch.css';

const IntelligentSearch = () => {
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const textareaRef = useRef(null);

  // Auto-resize textarea
  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [query]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!query.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await searchApi.intelligentSearch(query.trim());
      
      setResult({
        response: response.response || 'Không có phản hồi từ hệ thống.',
        status: response.status,
        timestamp: new Date()
      });
    } catch (error) {
      console.error('Search error:', error);
      let errorMsg = 'Xin lỗi, có lỗi xảy ra khi xử lý yêu cầu của bạn.';
      
      if (error.response?.status === 504) {
        errorMsg = 'Yêu cầu đang được xử lý quá lâu. Vui lòng thử lại với câu hỏi ngắn gọn hơn.';
      } else if (error.response?.status === 503) {
        errorMsg = 'Dịch vụ AI hiện tại không khả dụng. Vui lòng thử lại sau.';
      }

      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const formatResponse = (content) => {
    return content.split('\n\n').map((paragraph, index) => (
      <p key={index} className="response-paragraph">
        {paragraph}
      </p>
    ));
  };

  const suggestedQuestions = [
    "Quy định về điểm rèn luyện là gì?",
    "Điều kiện tốt nghiệp đại học?",
    "Cách tính điểm trung bình tích lũy?",
    "Quy định về học phí và miễn giảm?"
  ];

  const handleSuggestionClick = (suggestion) => {
    setQuery(suggestion);
    setResult(null);
    setError(null);
  };

  return (
    <div className="intelligent-search">
      <div className="search-container">
        {/* Header */}
        <div className="search-header">
          <div className="header-content">
            <div className="header-text">
              <h1>AI Document Search</h1>
              <p>Tìm kiếm thông minh tài liệu với trí tuệ nhân tạo</p>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="main-content">
          {/* Loading State */}
          {isLoading && (
            <div className="loading-container">
              <div className="loading-content">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <p>Đang tìm kiếm và phân tích thông tin...</p>
              </div>
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="error-container">
              <div className="error-content">
                <div className="error-avatar">⚠️</div>
                <div className="error-text">
                  <h3>Có lỗi xảy ra</h3>
                  <p>{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Results */}
          {result && (
            <div className="result-container">
              <div className="result-content">
                <div className="result-text">
                  <div className="result-response">
                    {formatResponse(result.response)}
                  </div>
                  <div className="result-timestamp">
                    {result.timestamp.toLocaleTimeString('vi-VN', { 
                      hour: '2-digit', 
                      minute: '2-digit' 
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Suggestions (show when no query and no result and not loading) */}
          {!query && !result && !isLoading && !error && (
            <div className="suggestions-container">
              <div className="suggestions-title">💡 Gợi ý câu hỏi:</div>
              <div className="suggestions-grid">
                {suggestedQuestions.map((suggestion, index) => (
                  <button
                    key={index}
                    className="suggestion-card"
                    onClick={() => handleSuggestionClick(suggestion)}
                  >
                    <span className="suggestion-text">{suggestion}</span>
                    <span className="suggestion-arrow">→</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Search Input */}
          <div className="input-section">
            <form onSubmit={handleSubmit} className="search-form">
              <div className="input-wrapper">
                <textarea
                  ref={textareaRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Nhập câu hỏi của bạn về quy định trường học..."
                  className="search-textarea"
                  disabled={isLoading}
                  rows={1}
                />
                
                <button 
                  type="submit" 
                  className={`send-button ${!query.trim() || isLoading ? 'disabled' : ''}`}
                  disabled={!query.trim() || isLoading}
                >
                  {isLoading ? (
                    <div className="loading-spinner">
                      <span className="spinner"></span>
                    </div>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <path d="M2 21l21-9L2 3v7l15 2-15 2v7z" fill="currentColor"/>
                    </svg>
                  )}
                </button>
              </div>
            </form>
            
            <div className="input-footer">
              <p>AI có thể mắc lỗi. Hãy kiểm tra thông tin quan trọng.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default IntelligentSearch; 