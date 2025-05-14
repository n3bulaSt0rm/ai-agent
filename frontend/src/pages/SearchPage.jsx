import { useState } from 'react';
import '../styles/SearchPage.css';

// Mock data for search results
const mockSearchResults = [
  {
    id: 1,
    document: {
      id: 1,
      title: 'Quy chế đào tạo đại học 2024',
      type: 'pdf'
    },
    content: 'Điểm rèn luyện được đánh giá bằng điểm số từ 0 đến 100. Điểm rèn luyện được phân thành các loại: xuất sắc (từ 90 đến 100 điểm), tốt (từ 80 đến 89 điểm), khá (từ 65 đến 79 điểm), trung bình (từ 50 đến 64 điểm), yếu (từ 35 đến 49 điểm) và kém (dưới 35 điểm).',
    page: 15,
    relevance: 95
  },
  {
    id: 2,
    document: {
      id: 1,
      title: 'Quy chế đào tạo đại học 2024',
      type: 'pdf'
    },
    content: 'Sinh viên bị cảnh báo kết quả học tập nếu điểm trung bình chung học kỳ đạt dưới 1,20 đối với học kỳ đầu của khóa học, dưới 1,40 đối với các học kỳ tiếp theo, hoặc điểm trung bình chung tích lũy đạt dưới 1,50.',
    page: 23,
    relevance: 82
  },
  {
    id: 3,
    document: {
      id: 2,
      title: 'Quy định về khảo thí và đánh giá kết quả học tập',
      type: 'pdf'
    },
    content: 'Điểm rèn luyện được sử dụng để xét học bổng, khen thưởng cuối mỗi học kỳ hoặc năm học. Điểm rèn luyện được lưu trong hồ sơ quản lý sinh viên, được sử dụng trong việc xét duyệt các chế độ chính sách và xét thôi học.',
    page: 8,
    relevance: 78
  },
  {
    id: 4,
    document: {
      id: 5,
      title: 'Quy chế rèn luyện sinh viên',
      type: 'pdf'
    },
    content: 'Đánh giá kết quả rèn luyện của sinh viên là đánh giá về ý thức, thái độ và kết quả học tập của sinh viên. Kết quả đánh giá rèn luyện được phân thành 5 loại: xuất sắc, tốt, khá, trung bình, yếu.',
    page: 3,
    relevance: 88
  }
];

// Mock AI response
const mockAiResponse = {
  answer: "Điểm rèn luyện là thang điểm đánh giá về ý thức, thái độ và kết quả học tập của sinh viên. Theo quy định, điểm rèn luyện được đánh giá bằng thang điểm từ 0-100 và phân loại như sau:\n\n- Xuất sắc: 90-100 điểm\n- Tốt: 80-89 điểm\n- Khá: 65-79 điểm\n- Trung bình: 50-64 điểm\n- Yếu: 35-49 điểm\n- Kém: dưới 35 điểm\n\nĐiểm rèn luyện được sử dụng để xét học bổng, khen thưởng, và các chế độ chính sách dành cho sinh viên.",
  sources: [
    { id: 1, document: 'Quy chế đào tạo đại học 2024', page: 15 },
    { id: 3, document: 'Quy định về khảo thí và đánh giá kết quả học tập', page: 8 },
    { id: 4, document: 'Quy chế rèn luyện sinh viên', page: 3 }
  ]
};

const SearchPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [activeTab, setActiveTab] = useState('ai');
  const [searchResults, setSearchResults] = useState([]);
  const [aiResponse, setAiResponse] = useState(null);

  const handleSearch = (e) => {
    e.preventDefault();
    
    if (!searchQuery.trim()) return;
    
    // Simulate search
    setIsSearching(true);
    
    // Mock API call
    setTimeout(() => {
      setSearchResults(mockSearchResults);
      setAiResponse(mockAiResponse);
      setIsSearching(false);
      setShowResults(true);
    }, 1500);
  };

  const handleSuggestionClick = (suggestion) => {
    setSearchQuery(suggestion);
    
    // Automatically search when clicking a suggestion
    setIsSearching(true);
    
    // Mock API call
    setTimeout(() => {
      setSearchResults(mockSearchResults);
      setAiResponse(mockAiResponse);
      setIsSearching(false);
      setShowResults(true);
    }, 1500);
  };

  return (
    <div className="page-container search-page">
      <header className="page-header">
        <div>
          <h1>Intelligent Search</h1>
          <p>Search through your regulations with AI assistance</p>
        </div>
      </header>
      
      <div className="search-container card">
        <div className="search-hero">
          <h2>Ask Questions About School Regulations</h2>
          <p>Our AI will find accurate information from processed documents</p>
        </div>
        
        <form onSubmit={handleSearch} className="search-form">
          <div className="search-box-large">
            <input 
              type="text" 
              className="search-input" 
              placeholder="Example: Quy định về điểm rèn luyện là gì?" 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <button 
              type="submit" 
              className="search-button"
              disabled={isSearching}
            >
              {isSearching ? (
                <>
                  <div className="spinner-small"></div>
                  <span>Searching...</span>
                </>
              ) : (
                <>
                  <i className="search-icon-white"></i>
                  <span>Search</span>
                </>
              )}
            </button>
          </div>
        </form>
        
        {!showResults && (
          <div className="search-suggestions">
            <h4>Suggested searches:</h4>
            <div className="suggestion-chips">
              <button 
                className="suggestion-chip"
                onClick={() => handleSuggestionClick("Quy định về điểm rèn luyện là gì?")}
              >
                Quy định về điểm rèn luyện
              </button>
              <button 
                className="suggestion-chip"
                onClick={() => handleSuggestionClick("Điều kiện tốt nghiệp đại học là gì?")}
              >
                Điều kiện tốt nghiệp
              </button>
              <button 
                className="suggestion-chip"
                onClick={() => handleSuggestionClick("Quy định về học phí và miễn giảm học phí?")}
              >
                Quy định về học phí
              </button>
              <button 
                className="suggestion-chip"
                onClick={() => handleSuggestionClick("Điều kiện xét học bổng như thế nào?")}
              >
                Điều kiện xét học bổng
              </button>
            </div>
          </div>
        )}
      </div>
      
      {showResults && (
        <div className="search-results">
          <div className="results-header">
            <h2>Search results for: <span className="search-term">"{searchQuery}"</span></h2>
            
            <div className="results-tabs">
              <button 
                className={`tab-button ${activeTab === 'ai' ? 'active' : ''}`}
                onClick={() => setActiveTab('ai')}
              >
                AI Answer
              </button>
              <button 
                className={`tab-button ${activeTab === 'documents' ? 'active' : ''}`}
                onClick={() => setActiveTab('documents')}
              >
                Document Matches <span className="result-count">{searchResults.length}</span>
              </button>
            </div>
          </div>
          
          <div className="results-content">
            {activeTab === 'ai' && aiResponse && (
              <div className="ai-answer-container">
                <div className="ai-answer card">
                  <div className="ai-header">
                    <div className="ai-avatar">
                      <i className="ai-icon-large"></i>
                    </div>
                    <div className="ai-info">
                      <h3>AI Assistant</h3>
                      <p>Powered by vector search and large language model</p>
                    </div>
                  </div>
                  
                  <div className="answer-content">
                    {aiResponse.answer.split('\n').map((paragraph, index) => (
                      <p key={index}>{paragraph}</p>
                    ))}
                  </div>
                  
                  <div className="answer-sources">
                    <h4>Sources:</h4>
                    <ul className="source-list">
                      {aiResponse.sources.map(source => (
                        <li key={source.id} className="source-item">
                          <i className="document-icon-small"></i>
                          <span className="source-name">{source.document}</span>
                          <span className="source-page">(Page {source.page})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  
                  <div className="feedback-buttons">
                    <button className="feedback-btn positive">
                      <i className="thumbs-up-icon"></i>
                      Helpful
                    </button>
                    <button className="feedback-btn negative">
                      <i className="thumbs-down-icon"></i>
                      Not Helpful
                    </button>
                  </div>
                </div>
                
                <div className="followup-questions card">
                  <h3>Follow-up Questions</h3>
                  <div className="question-list">
                    <button className="followup-question">
                      Làm thế nào để cải thiện điểm rèn luyện?
                    </button>
                    <button className="followup-question">
                      Điểm rèn luyện ảnh hưởng thế nào đến xét tốt nghiệp?
                    </button>
                    <button className="followup-question">
                      Cách tính điểm rèn luyện mỗi học kỳ?
                    </button>
                  </div>
                </div>
              </div>
            )}
            
            {activeTab === 'documents' && (
              <div className="document-results">
                {searchResults.map(result => (
                  <div key={result.id} className="result-card card">
                    <div className="result-header">
                      <div className={`document-type-small ${result.document.type}`}></div>
                      <h3 className="result-title">{result.document.title}</h3>
                      <span className="result-page">Page {result.page}</span>
                      <span className="relevance-badge" title="Relevance score">
                        {result.relevance}%
                      </span>
                    </div>
                    
                    <div className="result-content">
                      <p>{result.content}</p>
                    </div>
                    
                    <div className="result-actions">
                      <button className="link-btn">
                        <i className="view-doc-icon"></i>
                        View Document
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          <div className="search-footer card">
            <div className="new-search">
              <h3>Not finding what you're looking for?</h3>
              <form onSubmit={handleSearch} className="inline-search">
                <input 
                  type="text" 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Try a different search query..."
                  className="inline-search-input"
                />
                <button type="submit" className="inline-search-btn">
                  <i className="search-icon-small"></i>
                  Search
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SearchPage; 