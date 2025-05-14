# Hướng dẫn triển khai Backend và Messaging Service

## Tổng quan

Hướng dẫn này giúp bạn triển khai phần backend và messaging service của ứng dụng. Chúng ta sẽ sử dụng:

1. **Web Service**: Một FastAPI server cung cấp REST API
2. **Messaging Service**: Một dịch vụ messaging đơn giản được triển khai local (có thể chuyển sang Google Cloud PubSub)
3. **Mock Processing Service**: Một dịch vụ xử lý đơn giản để giả lập xử lý documents

## Yêu cầu

- Python 3.11 trở lên
- Docker và Docker Compose (tùy chọn)
- Các thư viện Python được liệt kê trong `requirements.txt`

## 1. Thiết lập Môi trường

### 1.1 Sử dụng môi trường ảo Python (Không cần nếu sử dụng Docker)

```bash

# hoặc
.venv\Scripts\activate  # Windows

# Cài đặt các thư viện
pip install -r requirements.txt
```

### 1.2 Cấu hình môi trường

Tạo file `.env` từ `env.example` và chỉnh sửa theo nhu cầu:

```bash
cp env.example .env
```

Các cấu hình quan trọng trong file `.env`:

```
# Sử dụng local messaging thay cho PubSub
USE_LOCAL_MESSAGING=true
PUBSUB_PDF_PROCESSING_TOPIC=pdf-processing-topic
PUBSUB_EMAIL_RESPONSE_TOPIC=email-response-topic

# Kết nối Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=regulations
```

## 2. Chạy Ứng dụng

### 2.1 Sử dụng Docker Compose (Đơn giản nhất)

```bash
# Khởi động toàn bộ stack
docker-compose up -d

# Kiểm tra log
docker-compose logs -f web
docker-compose logs -f processing
```

### 2.2 Chạy thủ công (Nếu không sử dụng Docker)

Bước 1: Khởi động Qdrant (Database Vector)

```bash
# Sử dụng Docker để chạy Qdrant (cách đơn giản nhất)
docker run -d -p 6333:6333 -p 6334:6334 -v $(pwd)/qdrant_data:/qdrant/storage qdrant/qdrant
```

Bước 2: Khởi động Web Service

```bash
python backend/cmd/web_service.py
```

Bước 3: Khởi động Processing Service

```bash
python backend/cmd/processing_service.py
```



Các API của web_service:

- **Xác thực**: `/api/auth/token` - Lấy JWT token (mặc định: admin/admin123)
- **Upload file**: `/api/files/upload` - Tải file PDF lưu trên GCS, đồng thời lưu lại các thông tin vào SQLite (uuid, linkfile, fileSize, pages(số trang), Status(mới upload thì là pending) Description, fileCreatedAt(cho chọn ngày tháng trong lúc upload), UploadAt, CreatedAt, UpdatedAt)
- **Update file**: `/api/files/update` - Update status, description cho file
- **Search file**: `/api.files/search` - Search file theo tên file
- **Xử lý file**: `/api/files/{id}/process` - Chọn file để xử lý
- **Soft Delete file**: `DELETE /api/files/{id}` - Đánh dấu file là đã xóa (soft delete)
- **Restore file**: `POST /api/files/{id}/restore` - Khôi phục file đã xóa

File được upload thành công sẽ được hiển thị lên trên frontend (FileList.jsx)

Workflow xử lý file của processing_service:
User click váo button process action trong page Documents (FileList.jsx) gọi /api/files/{id}/process ->gửi message mang thông tin link file, uuid, action, fileCreatedAt

processing_service sẽ thực hiện:
1. Lắng nghe topic file_handler để xem có file nào cần xử lý không
2. Nếu có thì đọc xem action là gì(có 3 loại action là process, restore, delete) (khi này icon của file xử lý trong FileList.jsx sẽ chuyển thành icon proccessing, nếu action là process thì là icon processing màu xanh nước biển, nếu action là delete thì là icon processing màu đỏ, nếu action là restore thì process là icon processing màu xanh lá)
3. Đối với action là: process thì thực hiện xử lý xong thì lưu lại vào qdrant và gọi hàm callback tới web_service để thực hiện lưu lại status cho file là completed
   Đối với action là delete thì thực hiện xử lý tìm kiếm tất cả các chunk có uuid trong metadata khớp với uuid trong message thì chuyển is_deleted trong metadata thành true và gọi hàm callback tới web_service để thực hiện lưu lại status cho file là deleted
   Đối với action là restore thì thực hiện xử lý tìm kiếm tất cả các chunk có uuid trong metadata khớp với uuid trong message thì chuyển is_deleted trong metadata thành false và gọi hàm callback tới web_service để thực hiện lưu lại status cho file là completed



## 4. Cấu trúc Dự án

```
backend/
├── core/                  # Cấu hình, xác thực
├── db/                    # Module cơ sở dữ liệu (SQLite, Qdrant)
├── services/
│   ├── messaging/         # Dịch vụ messaging
│   │   ├── __init__.py    # Factory cho messaging client
│   │   ├── local.py       # Implementation local cho development
│   │   ├── pubsub.py      # Google Cloud PubSub implementation
│   ├── processing/        # Dịch vụ xử lý file
│   │   ├── main.py        # Endpoint chính của processing service
│   ├── web/               # Web API service
│   │   ├── api/           # API endpoints
│   │   ├── main.py        # FastAPI app
├── utils/                 # Các tiện ích
```

## 5. Tùy chỉnh và Mở rộng

### 5.1 Sử dụng Google Cloud PubSub

Để chuyển sang dùng Google Cloud PubSub thay vì messaging local:

1. Tạo project và cấu hình service account trong Google Cloud
2. Cập nhật `.env`:
```
USE_LOCAL_MESSAGING=false
GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json
GOOGLE_CLOUD_PROJECT=your-project-id
```

### 5.2 Triển khai lên Production

Để triển khai lên môi trường production:

1. Sử dụng container orchestration như Kubernetes
2. Cấu hình các biến môi trường phù hợp
3. Sử dụng persistent storage cho database
4. Đảm bảo security bằng cách giới hạn CORS, sử dụng HTTPS

### 5.3 Cấu hình Database Qdrant

Qdrant là vector database được sử dụng để lưu trữ và truy vấn vector embeddings. Để triển khai đầy đủ, bạn cần:

1. Cập nhật Qdrant schema để hỗ trợ trường `is_deleted` trong metadata
2. Triển khai hàm query với filter loại bỏ các documents bị đánh dấu `is_deleted=true`
3. Cập nhật vector_store.py để thêm các phương thức quản lý trạng thái `is_deleted`

## 6. Xử lý Sự cố

### 6.1 Web Service không khởi động

- Kiểm tra log: `docker-compose logs web`
- Kiểm tra cấu hình trong `.env`
- Đảm bảo port 8000 không bị sử dụng bởi ứng dụng khác

### 6.2 Processing Service không nhận messages

- Kiểm tra log: `docker-compose logs processing`
- Đảm bảo `USE_LOCAL_MESSAGING=true` trong cả web và processing service
- Kiểm tra xem web service đã khởi động thành công chưa

### 6.3 Qdrant không kết nối được

- Kiểm tra Qdrant đã chạy: `docker ps`
- Kiểm tra cấu hình `QDRANT_HOST` và `QDRANT_PORT` trong `.env`

### 6.4 Soft Delete hoặc Restore không hoạt động

- Kiểm tra báo lỗi trong log của Web Service và Processing Service
- Đảm bảo database SQLite có trường `previous_status` trong bảng `pdf_files`
- Kiểm tra messaging service đang hoạt động bình thường

## 7. Chú ý

- Mock processing service chỉ giả lập việc xử lý document, không thực sự OCR hoặc tạo embeddings.
- Để triển khai đầy đủ processing service, cần bổ sung code OCR và embedding.
- Dữ liệu lưu trong Docker sẽ bị mất khi xóa container. Sử dụng volumes để giữ dữ liệu.
- Tính năng soft delete và restore chỉ hoạt động đầy đủ khi cấu hình mở rộng Qdrant để hỗ trợ lọc theo `is_deleted`. 