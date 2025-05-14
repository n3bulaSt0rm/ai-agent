#!/bin/bash
# Script triển khai AI Agent backend

set -e

echo "=== Triển khai AI Agent Backend và Messaging Service ==="
echo

# Kiểm tra Docker
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo "✅ Docker và Docker Compose đã được cài đặt"
else
    echo "❌ Docker hoặc Docker Compose chưa được cài đặt."
    echo "Vui lòng cài đặt Docker và Docker Compose: https://docs.docker.com/get-docker/"
    exit 1
fi

# Kiểm tra file .env
if [ -f ".env" ]; then
    echo "✅ File .env đã tồn tại"
else
    echo "📝 Tạo file .env từ env.example..."
    cp env.example .env
    echo "✅ Đã tạo file .env, vui lòng kiểm tra và chỉnh sửa nếu cần thiết"
fi

# Đảm bảo thư mục data tồn tại
mkdir -p data
echo "✅ Đã tạo thư mục data"

# Đảm bảo quyền thực thi cho các script
chmod +x run_web_service.py
chmod +x run_processing_service.py
echo "✅ Đã cấp quyền thực thi cho các script"

# Khởi động dịch vụ
echo "🚀 Khởi động các dịch vụ với Docker Compose..."
docker-compose down
docker-compose up -d

# Kiểm tra trạng thái
echo
echo "=== Trạng thái dịch vụ ==="
docker-compose ps

# Hiển thị thông tin endpoints
echo
echo "=== Thông tin Endpoints ==="
echo "📝 API Documentation: http://localhost:8000/docs"
echo "📝 Health Check: http://localhost:8000/health"
echo
echo "👉 Xem DEPLOYMENT_GUIDE.md để biết thêm thông tin"
echo
echo "=== Triển khai hoàn tất ===" 