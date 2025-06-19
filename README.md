# AI-Agent PDF Management

## Hướng dẫn chạy dự án

### 1. Chuẩn bị

1.  **Clone Repository:**
    ```bash
    git clone <your-repository-url>
    cd ai-agent
    ```

2.  **Cấu hình môi trường:**
    Sao chép `env.example` thành `.env` và điền các thông tin cần thiết.
    ```bash
    cp env.example .env
    ```
    *Lưu ý: Bạn cần điền đầy đủ các API keys và credentials. Đảm bảo `FRONTEND_URL` trong file `.env` khớp với địa chỉ của frontend.*

### 2. Cách chạy

1.  **Khởi chạy Qdrant:**
    ```bash
    docker run -p 6333:6333 -p 6334:6334 \
        -v $(pwd)/qdrant_data:/qdrant/storage \
        qdrant/qdrant
    ```

2.  **Khởi chạy Backend:**
    Mở một terminal mới, di chuyển vào thư mục `backend`, cài đặt và chạy các service.
    ```bash
    cd backend
    python -m venv venv
    # Kích hoạt môi trường ảo
    # Windows: .\venv\Scripts\activate | macOS/Linux: source venv/bin/activate
    pip install -r ../requirements.txt
    
    # Chạy các service (mỗi lệnh trong một terminal riêng)
    python cmd/web_service.py
    python cmd/processing_service.py
    ```

3.  **Khởi chạy Frontend:**
    Mở một terminal khác, di chuyển vào `frontend`, cài đặt và chạy.
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

4.  **Dừng ứng dụng:**
    Nhấn `Ctrl + C` trong từng cửa sổ terminal đang chạy.
