import os
import email
from email import policy
from pathlib import Path
from collections import defaultdict
import mimetypes

def is_image_file(filename, content_type=None):
    """
    Kiểm tra xem file có phải là ảnh không
    """
    # Các extension ảnh phổ biến
    image_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', 
        '.webp', '.ico', '.svg', '.psd', '.raw', '.heic', '.heif'
    }
    
    # Kiểm tra theo extension
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in image_extensions:
            return True
    
    # Kiểm tra theo MIME type
    if content_type:
        if content_type.startswith('image/'):
            return True
    
    # Guess MIME type từ filename
    if filename:
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type and guessed_type.startswith('image/'):
            return True
    
    return False

def extract_images_from_email(eml_file_path):
    """
    Trích xuất thông tin ảnh từ một file .eml
    """
    try:
        with open(eml_file_path, 'rb') as f:
            msg = email.message_from_bytes(f.read(), policy=policy.default)
        
        images = []
        
        # Lấy thông tin cơ bản của email
        subject = msg.get('Subject', 'No Subject')
        date = msg.get('Date', '')
        sender = msg.get('From', '')
        
        # Tìm attachments
        for part in msg.walk():
            # Bỏ qua multipart containers
            if part.get_content_maintype() == 'multipart':
                continue
            
            # Lấy filename
            filename = part.get_filename()
            content_type = part.get_content_type()
            
            # Kiểm tra xem có phải ảnh không
            if is_image_file(filename, content_type):
                # Lấy size nếu có
                content = part.get_payload(decode=True)
                size = len(content) if content else 0
                
                image_info = {
                    'filename': filename or 'unnamed_image',
                    'content_type': content_type,
                    'size': size,
                    'size_mb': round(size / (1024 * 1024), 2) if size > 0 else 0
                }
                images.append(image_info)
        
        return {
            'email_file': Path(eml_file_path).name,
            'subject': subject,
            'date': date,
            'sender': sender,
            'images': images,
            'image_count': len(images)
        }
        
    except Exception as e:
        print(f"Lỗi khi đọc file {eml_file_path}: {e}")
        return None

def analyze_images_in_threads(threads_folder):
    """
    Phân tích ảnh trong tất cả các email threads
    """
    threads_folder = Path(threads_folder)
    
    if not threads_folder.exists():
        print(f"Folder không tồn tại: {threads_folder}")
        return
    
    print(f"🔍 Phân tích ảnh trong folder: {threads_folder}")
    
    # Thống kê tổng quan
    total_threads = 0
    threads_with_images = 0
    total_emails = 0
    emails_with_images = 0
    total_images = 0
    
    # Chi tiết theo thread
    thread_details = []
    
    # Duyệt qua tất cả các folder con (threads)
    for thread_folder in threads_folder.iterdir():
        if not thread_folder.is_dir():
            continue
        
        total_threads += 1
        thread_name = thread_folder.name
        
        # Phân tích các email trong thread
        eml_files = list(thread_folder.glob("*.eml"))
        thread_total_emails = len(eml_files)
        thread_emails_with_images = 0
        thread_total_images = 0
        thread_image_details = []
        
        for eml_file in eml_files:
            total_emails += 1
            email_info = extract_images_from_email(eml_file)
            
            if email_info and email_info['image_count'] > 0:
                emails_with_images += 1
                thread_emails_with_images += 1
                thread_total_images += email_info['image_count']
                total_images += email_info['image_count']
                thread_image_details.append(email_info)
        
        # Lưu thông tin thread nếu có ảnh
        if thread_total_images > 0:
            threads_with_images += 1
            thread_details.append({
                'name': thread_name,
                'total_emails': thread_total_emails,
                'emails_with_images': thread_emails_with_images,
                'total_images': thread_total_images,
                'image_details': thread_image_details
            })
    
    # Sắp xếp threads theo số lượng ảnh
    thread_details.sort(key=lambda x: x['total_images'], reverse=True)
    
    return {
        'summary': {
            'total_threads': total_threads,
            'threads_with_images': threads_with_images,
            'total_emails': total_emails,
            'emails_with_images': emails_with_images,
            'total_images': total_images
        },
        'thread_details': thread_details
    }

def print_image_analysis(analysis_result):
    """
    In kết quả phân tích ảnh
    """
    if not analysis_result:
        print("Không có dữ liệu để phân tích")
        return
    
    summary = analysis_result['summary']
    thread_details = analysis_result['thread_details']
    
    print("\n" + "="*80)
    print("📊 THỐNG KÊ ẢNH TRONG EMAIL THREADS")
    print("="*80)
    
    print(f"\n🎯 TỔNG QUAN:")
    print(f"   - Tổng số threads: {summary['total_threads']}")
    print(f"   - Threads chứa ảnh: {summary['threads_with_images']}")
    print(f"   - Tỷ lệ threads có ảnh: {summary['threads_with_images']/summary['total_threads']*100:.1f}%")
    print(f"   - Tổng số emails: {summary['total_emails']}")
    print(f"   - Emails chứa ảnh: {summary['emails_with_images']}")
    print(f"   - Tỷ lệ emails có ảnh: {summary['emails_with_images']/summary['total_emails']*100:.1f}%")
    print(f"   - Tổng số ảnh: {summary['total_images']}")
    
    if thread_details:
        print(f"\n📂 CHI TIẾT THREADS CHỨA ẢNH (Top 20):")
        
        for i, thread in enumerate(thread_details[:20], 1):
            print(f"\n{i:2d}. 📁 {thread['name']}")
            print(f"      📧 Emails: {thread['total_emails']} | Có ảnh: {thread['emails_with_images']}")
            print(f"      🖼️  Tổng ảnh: {thread['total_images']}")
            
            # Hiển thị 3 email có nhiều ảnh nhất trong thread
            top_emails = sorted(thread['image_details'], 
                              key=lambda x: x['image_count'], reverse=True)[:3]
            
            for j, email_info in enumerate(top_emails, 1):
                print(f"         {j}. {email_info['email_file']} - {email_info['image_count']} ảnh")
                if email_info['subject']:
                    subject_short = email_info['subject'][:60] + "..." if len(email_info['subject']) > 60 else email_info['subject']
                    print(f"            📧 {subject_short}")
                
                # Hiển thị top 3 ảnh lớn nhất
                top_images = sorted(email_info['images'], 
                                  key=lambda x: x['size'], reverse=True)[:3]
                for img in top_images:
                    print(f"            🖼️  {img['filename']} ({img['size_mb']} MB)")
    
    # Thống kê theo kích thước ảnh
    print(f"\n📈 THỐNG KÊ KÍCH THƯỚC:")
    all_images = []
    total_size = 0
    
    for thread in thread_details:
        for email_info in thread['image_details']:
            for img in email_info['images']:
                all_images.append(img)
                total_size += img['size']
    
    if all_images:
        all_images.sort(key=lambda x: x['size'], reverse=True)
        print(f"   - Tổng dung lượng ảnh: {total_size / (1024*1024):.2f} MB")
        print(f"   - Ảnh lớn nhất: {all_images[0]['filename']} ({all_images[0]['size_mb']} MB)")
        print(f"   - Ảnh nhỏ nhất: {all_images[-1]['filename']} ({all_images[-1]['size_mb']} MB)")
        print(f"   - Trung bình: {(total_size/len(all_images))/(1024*1024):.2f} MB/ảnh")
    
    # Thống kê theo loại file
    print(f"\n📋 THỐNG KÊ THEO LOẠI FILE:")
    file_types = defaultdict(int)
    for thread in thread_details:
        for email_info in thread['image_details']:
            for img in email_info['images']:
                ext = Path(img['filename']).suffix.lower() if img['filename'] else 'unknown'
                file_types[ext] += 1
    
    for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {ext if ext else 'Không rõ'}: {count} ảnh")

def export_image_report(analysis_result, output_file):
    """
    Xuất báo cáo ra file CSV
    """
    import csv
    
    if not analysis_result:
        return
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Header
        writer.writerow([
            'Thread Name', 'Total Emails', 'Emails with Images', 'Total Images',
            'Email File', 'Email Subject', 'Image Filename', 'Image Type', 'Size MB'
        ])
        
        # Data
        for thread in analysis_result['thread_details']:
            for email_info in thread['image_details']:
                for img in email_info['images']:
                    writer.writerow([
                        thread['name'],
                        thread['total_emails'],
                        thread['emails_with_images'],
                        thread['total_images'],
                        email_info['email_file'],
                        email_info['subject'],
                        img['filename'],
                        img['content_type'],
                        img['size_mb']
                    ])
    
    print(f"📄 Đã xuất báo cáo chi tiết ra: {output_file}")

if __name__ == "__main__":
    # Đường dẫn folder chứa các threads
    threads_folder = r"D:\Project\DATN_HUST\ai-agent\data\eml_threads"
    
    # Đường dẫn file báo cáo (optional)
    report_file = r"D:\Project\DATN_HUST\ai-agent\data\image_analysis_report.csv"
    
    print("🖼️  Bắt đầu phân tích ảnh trong email threads...")
    
    # Phân tích
    analysis_result = analyze_images_in_threads(threads_folder)
    
    if analysis_result:
        # In kết quả
        print_image_analysis(analysis_result)
        
        # Hỏi có muốn xuất báo cáo không
        print(f"\n❓ Bạn có muốn xuất báo cáo chi tiết ra file CSV?")
        choice = input("Nhấn Enter để xuất báo cáo, hoặc 'n' để bỏ qua: ").strip().lower()
        
        if choice != 'n':
            export_image_report(analysis_result, report_file)
        else:
            print("✅ Chỉ hiển thị thống kê, không xuất báo cáo.")
    else:
        print("❌ Không thể phân tích dữ liệu.") 