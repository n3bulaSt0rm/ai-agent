import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import '../styles/FileDetail.css';

// Mock data
const mockDocuments = [
  { 
    id: 1, 
    title: 'Quy chế đào tạo đại học 2024', 
    size: '2.4 MB', 
    uploadDate: '2024-07-15', 
    status: 'processed',
    pages: 42,
    type: 'pdf',
    uploadedBy: 'admin',
    description: 'Quy chế đào tạo trình độ đại học theo hệ thống tín chỉ của trường Đại học Bách khoa Hà Nội.',
    sampleContent: [
      { 
        page: 1, 
        text: 'CHƯƠNG I: NHỮNG QUY ĐỊNH CHUNG\n\nĐiều 1. Phạm vi điều chỉnh và đối tượng áp dụng\n1. Quy chế này quy định về đào tạo trình độ đại học theo hệ thống tín chỉ, bao gồm: chương trình đào tạo, tổ chức đào tạo; kiểm tra, thi học phần; xét và công nhận tốt nghiệp.' 
      },
      { 
        page: 2, 
        text: 'Điều 2. Chương trình đào tạo\n1. Chương trình đào tạo (sau đây gọi tắt là chương trình) cần thể hiện rõ: trình độ đào tạo; đối tượng đào tạo, điều kiện nhập học và điều kiện tốt nghiệp; mục tiêu đào tạo, chuẩn kiến thức, kỹ năng của người học khi tốt nghiệp; khối lượng kiến thức lý thuyết, thực hành, thực tập; kế hoạch đào tạo theo thời gian thiết kế; phương pháp và hình thức đào tạo; cách thức đánh giá kết quả học tập; các điều kiện thực hiện chương trình.'
      }
    ]
  },
  { 
    id: 2, 
    title: 'Quy định về khảo thí và đánh giá kết quả học tập', 
    size: '1.8 MB', 
    uploadDate: '2024-07-10', 
    status: 'processed',
    pages: 35,
    type: 'pdf',
    uploadedBy: 'admin',
    description: 'Quy định về công tác khảo thí và đánh giá kết quả học tập của sinh viên tại trường Đại học Bách khoa Hà Nội.',
    sampleContent: [
      { 
        page: 1, 
        text: 'CHƯƠNG I: QUY ĐỊNH CHUNG\n\nĐiều 1. Phạm vi điều chỉnh và đối tượng áp dụng\n1. Văn bản này quy định về công tác khảo thí và đánh giá kết quả học tập của sinh viên trong quá trình đào tạo tại Trường Đại học Bách khoa Hà Nội.' 
      }
    ]
  },
];

const FileDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  
  useEffect(() => {
    // Simulate API call to fetch document details
    const fetchDocument = async () => {
      setLoading(true);
      try {
        // In a real app, you would fetch data from an API
        const doc = mockDocuments.find(doc => doc.id === parseInt(id));
        
        if (doc) {
          setDocument(doc);
        } else {
          // Document not found
          navigate('/files', { replace: true });
        }
      } catch (error) {
        console.error('Error fetching document:', error);
      } finally {
        setLoading(false);
      }
    };
    
    fetchDocument();
  }, [id, navigate]);
  
  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };
  
  const confirmDelete = () => {
    // In a real app, you would make an API call to delete the document
    setShowDeleteConfirm(false);
    navigate('/files', { replace: true });
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
      <header className="page-header">
        <div className="header-back-button">
          <Link to="/files" className="back-button">
            <i className="back-icon"></i>
            <span>Back to all documents</span>
          </Link>
        </div>
        <div className="header-actions">
          <button className="btn-secondary">
            <i className="icon download-icon"></i>
            Download
          </button>
          <button className="btn-danger" onClick={handleDelete}>
            <i className="icon delete-icon"></i>
            Delete
          </button>
        </div>
      </header>
      
      <div className="document-hero">
        <div className="document-icon-large pdf"></div>
        <div className="document-hero-content">
          <h1>{document.title}</h1>
          <div className="document-meta">
            <span className="meta-item">
              <i className="icon file-icon"></i>
              {document.size}
            </span>
            <span className="meta-item">
              <i className="icon pages-icon"></i>
              {document.pages} pages
            </span>
            <span className="meta-item">
              <i className="icon calendar-icon"></i>
              Uploaded on {document.uploadDate}
            </span>
            <span className="meta-item">
              <i className="icon user-icon"></i>
              by {document.uploadedBy}
            </span>
            <span className={`status-badge ${document.status}`}>
              {document.status === 'processed' ? 'Processed' : 'Processing'}
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
              <h2>Document Information</h2>
              <p className="document-description">{document.description}</p>
              
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
                  <div className="detail-label">Upload date</div>
                  <div className="detail-value">{document.uploadDate}</div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Status</div>
                  <div className="detail-value">
                    <span className={`status-badge ${document.status}`}>
                      {document.status === 'processed' ? 'Processed' : 'Processing'}
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
      
      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="modal-overlay" onClick={() => setShowDeleteConfirm(false)}>
          <div className="modal-content confirm-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Confirm Deletion</h2>
              <button className="close-btn" onClick={() => setShowDeleteConfirm(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="confirm-message">
                <div className="warning-icon"></div>
                <p>Are you sure you want to delete <strong>{document.title}</strong>?</p>
                <p className="warning-text">This action cannot be undone. All data associated with this document will be permanently removed.</p>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowDeleteConfirm(false)}>Cancel</button>
              <button className="btn-danger" onClick={confirmDelete}>Delete Document</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileDetail; 