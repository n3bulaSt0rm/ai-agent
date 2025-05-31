# AI Agent for School Regulations

Hệ thống toàn diện để xử lý và quản lý các tài liệu quy định của trường học với khả năng OCR, tìm kiếm ngữ nghĩa, và giao diện quản lý.

## Kiến trúc

Hệ thống tuân theo mô hình kiến trúc sạch với sự phân tách rõ ràng giữa các thành phần:

### Backend

- `backend/core/` - Các module cấu hình cốt lõi và xác thực
- `backend/db/` - Các module cơ sở dữ liệu
  - `metadata.py` - SQLite cho metadata của file
  - `vector_store.py` - Qdrant cho lưu trữ vector
- `backend/services/` - Các module dịch vụ:
  - `web/` - Dịch vụ API web (FastAPI)
  - `processing/` - Dịch vụ xử lý PDF
  - `messaging/` - Dịch vụ truyền tin (RabbitMQ)
    - `email_handler.py` - Dịch vụ xử lý email từ Gmail
- `backend/utils/` - Các module tiện ích (S3, xử lý văn bản, v.v.)

### Frontend

- SPA dựa trên React với Vite và Chakra UI
- Các component cho xác thực, quản lý file, và tìm kiếm ngữ nghĩa

## Cài đặt và Thiết lập

### Yêu cầu

- Python 3.11 hoặc cao hơn
- Node.js 16 hoặc cao hơn
- Docker và Docker Compose (tùy chọn)
- Amazon AWS S3 bucket
- Tài khoản Gmail với OAuth2 credentials
- DeepSeek API key

### Thiết lập môi trường phát triển

1. Clone repository này
2. Tạo môi trường ảo Python:
   ```
   python -m venv .venv
   source .venv/bin/activate  # Trên Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Thiết lập biến môi trường:
   ```
   # Sao chép file env.example thành .env
   cp env.example .env
   
   # Chỉnh sửa .env với cấu hình của bạn, đặc biệt là:
   # - DATABASE_PATH: đường dẫn đến file SQLite
   # - AWS_ACCESS_KEY_ID và AWS_SECRET_ACCESS_KEY: thông tin xác thực AWS
   # - S3_BUCKET_NAME: tên bucket Amazon S3
   # - GMAIL_CREDENTIALS_PATH: đường dẫn đến file OAuth credentials
   # - DEEPSEEK_API_KEY: API key của DeepSeek
   # - AZURE_DOCUMENT_ENDPOINT và AZURE_DOCUMENT_KEY: API Azure Document Intelligence
   ```
4. Cài đặt phụ thuộc cho frontend:
   ```
   cd frontend
   npm install
   ```

### Thiết lập Gmail API

1. Tạo project trên Google Cloud Console
2. Bật Gmail API trong project
3. Tạo OAuth credentials:
   - Loại: Desktop application
   - Tải xuống file credentials.json và lưu vào thư mục gốc dự án
4. Khi chạy dịch vụ email lần đầu, bạn sẽ được yêu cầu xác thực trong trình duyệt

## Chạy các dịch vụ

### Chạy backend thủ công

#### 1. Chạy web service (API):
```
python -m uvicorn backend.services.web.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Chạy processing service:
```
python -m backend.services.processing.main
```

#### 3. Chạy dịch vụ xử lý email:
```
python run_gmail_service.py
```

### Chạy frontend thủ công:
```
cd frontend
npm run dev
```

### Sử dụng Docker Compose (tùy chọn)

```
docker-compose up -d
```

## Cài đặt Qdrant (Database vector)

### Sử dụng Docker (khuyến nghị):
```
docker run -p 6333:6333 -p 6334:6334 -v $(pwd)/qdrant_data:/qdrant/storage qdrant/qdrant
```

### Hoặc tải và cài đặt trực tiếp từ trang chủ:
https://qdrant.tech/documentation/install/

## Sử dụng API

Sau khi khởi động web service, bạn có thể:

1. Truy cập tài liệu API tại: http://localhost:8000/docs
2. Truy cập giao diện người dùng tại: http://localhost:3000 (nếu frontend đang chạy)

### Các API chính:

- **Xác thực**: `/api/auth/token` - Lấy JWT token
- **Upload file**: `/api/files/upload` - Tải lên file PDF
- **Xử lý file**: `/api/files/{id}/process` - Xử lý file đã tải lên
- **Tìm kiếm ngữ nghĩa**: `/api/query/search` - Tìm kiếm trong nội dung PDF

## Luồng xử lý chính

### Xử lý tài liệu PDF

1. Upload file PDF thông qua web API
2. File được lưu trữ trong Amazon S3
3. Yêu cầu xử lý được gửi đến processing service thông qua RabbitMQ
4. PDF được xử lý với OCR để trích xuất văn bản
5. Văn bản được chia thành các đoạn nhỏ và tạo embedding vectors
6. Vectors được lưu trong Qdrant để tìm kiếm
7. Metadata được cập nhật trong SQLite
8. Người dùng có thể thực hiện tìm kiếm ngữ nghĩa trên nội dung đã xử lý

### Xử lý email tự động

1. Dịch vụ email theo dõi các email mới trong hòm thư Gmail
2. Khi có email mới, dịch vụ trích xuất nội dung
3. Nội dung được sử dụng để truy vấn Qdrant tìm kiếm thông tin liên quan
4. Dịch vụ gửi truy vấn và kết quả từ Qdrant đến DeepSeek API
5. DeepSeek API tạo phản hồi email dựa trên thông tin
6. Email phản hồi được tạo thành bản nháp trong Gmail
7. Email gốc được đánh dấu là đã đọc

## Xác thực

Thông tin đăng nhập mặc định:
- Tên người dùng: admin
- Mật khẩu: admin123

Nên thay đổi trong file .env cho môi trường sản xuất.

## Gỡ lỗi và Khắc phục sự cố

### Kết nối tới Qdrant thất bại:
- Kiểm tra xem Qdrant có đang chạy không
- Xác minh QDRANT_HOST và QDRANT_PORT trong .env
- Thử kết nối trực tiếp: `curl http://localhost:6333/collections`

### Lỗi Gmail API:
- Kiểm tra file credentials.json đã tồn tại và đúng cấu trúc
- Kiểm tra quá trình xác thực đã hoàn tất (token.json đã được tạo)
- Kiểm tra quyền của ứng dụng trong Google Cloud Console 