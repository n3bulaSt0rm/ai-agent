import os
import email
from email import policy
from pathlib import Path
import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
import mimetypes
import hashlib

def clean_text(text):
    """
    Làm sạch text content
    """
    if not text:
        return ""
    
    # Loại bỏ excessive whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Loại bỏ HTML tags cơ bản
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode HTML entities
    import html
    text = html.unescape(text)
    
    return text.strip()

def extract_email_content(eml_file_path):
    """
    Trích xuất nội dung text và attachments từ email
    """
    try:
        with open(eml_file_path, 'rb') as f:
            msg = email.message_from_bytes(f.read(), policy=policy.default)
        
        # Lấy metadata
        subject = msg.get('Subject', 'No Subject')
        sender = msg.get('From', 'Unknown Sender')
        recipient = msg.get('To', 'Unknown Recipient')
        date_str = msg.get('Date', '')
        
        # Parse date
        parsed_date = None
        if date_str:
            try:
                parsed_date = parsedate_to_datetime(date_str)
            except:
                pass
        
        # Trích xuất text content
        text_content = ""
        html_content = ""
        
        # Lấy text từ email body
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        text_content += part.get_content()
                    except:
                        text_content += str(part.get_payload(decode=True), errors='ignore')
                elif content_type == "text/html":
                    try:
                        html_content += part.get_content()
                    except:
                        html_content += str(part.get_payload(decode=True), errors='ignore')
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                try:
                    text_content = msg.get_content()
                except:
                    text_content = str(msg.get_payload(decode=True), errors='ignore')
            elif content_type == "text/html":
                try:
                    html_content = msg.get_content()
                except:
                    html_content = str(msg.get_payload(decode=True), errors='ignore')
        
        # Nếu không có text plain, convert từ HTML
        if not text_content and html_content:
            # Simple HTML to text conversion
            import re
            text_content = re.sub(r'<[^>]+>', '', html_content)
            text_content = re.sub(r'\s+', ' ', text_content)
        
        # Trích xuất attachments (images và files khác)
        attachments = []
        images = []
        
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            
            filename = part.get_filename()
            content_type = part.get_content_type()
            
            if filename:  # Có attachment
                try:
                    content = part.get_payload(decode=True)
                    if content:
                        attachment_info = {
                            'filename': filename,
                            'content_type': content_type,
                            'size': len(content),
                            'content': content
                        }
                        
                        # Phân loại ảnh vs file khác
                        if is_image_content_type(content_type) or is_image_filename(filename):
                            images.append(attachment_info)
                        else:
                            attachments.append(attachment_info)
                except Exception as e:
                    print(f"Lỗi khi trích xuất attachment {filename}: {e}")
        
        return {
            'metadata': {
                'subject': subject,
                'sender': sender,
                'recipient': recipient,
                'date_str': date_str,
                'parsed_date': parsed_date,
                'filename': Path(eml_file_path).name
            },
            'content': {
                'text': clean_text(text_content),
                'html': html_content
            },
            'images': images,
            'attachments': attachments
        }
        
    except Exception as e:
        print(f"Lỗi khi đọc file {eml_file_path}: {e}")
        return None

def is_image_content_type(content_type):
    """Kiểm tra content type có phải ảnh không"""
    return content_type and content_type.startswith('image/')

def is_image_filename(filename):
    """Kiểm tra filename có phải ảnh không"""
    if not filename:
        return False
    
    image_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
        '.webp', '.ico', '.svg', '.psd', '.raw', '.heic', '.heif'
    }
    
    return Path(filename).suffix.lower() in image_extensions

def generate_safe_filename(original_name, existing_names=None):
    """
    Tạo tên file an toàn, tránh trùng lặp
    """
    if existing_names is None:
        existing_names = set()
    
    # Làm sạch tên file
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', original_name)
    safe_name = re.sub(r'_+', '_', safe_name)
    safe_name = safe_name.strip('_ ')
    
    if not safe_name:
        safe_name = "unnamed_file"
    
    # Xử lý trùng lặp
    if safe_name not in existing_names:
        existing_names.add(safe_name)
        return safe_name
    
    # Thêm suffix nếu trùng
    name_part, ext_part = os.path.splitext(safe_name)
    counter = 1
    
    while True:
        new_name = f"{name_part}_{counter}{ext_part}"
        if new_name not in existing_names:
            existing_names.add(new_name)
            return new_name
        counter += 1

def process_single_thread(thread_folder, output_folder):
    """
    Xử lý một thread: chuyển đổi thành text + images
    """
    thread_folder = Path(thread_folder)
    thread_name = thread_folder.name
    
    # Tạo output folder cho thread này
    thread_output = Path(output_folder) / f"processed_{thread_name}"
    thread_output.mkdir(parents=True, exist_ok=True)
    
    # Tạo sub-folders
    texts_folder = thread_output / "texts"
    images_folder = thread_output / "images"
    attachments_folder = thread_output / "attachments"
    
    texts_folder.mkdir(exist_ok=True)
    images_folder.mkdir(exist_ok=True)
    attachments_folder.mkdir(exist_ok=True)
    
    # Lấy tất cả file .eml
    eml_files = sorted(list(thread_folder.glob("*.eml")))
    
    if not eml_files:
        print(f"Không tìm thấy file .eml trong {thread_folder}")
        return None
    
    # Xử lý từng email
    thread_data = {
        'thread_name': thread_name,
        'total_emails': len(eml_files),
        'processed_date': datetime.now().isoformat(),
        'emails': [],
        'summary': {
            'total_images': 0,
            'total_attachments': 0,
            'total_text_length': 0
        }
    }
    
    used_filenames = set()
    
    for i, eml_file in enumerate(eml_files, 1):
        print(f"   Xử lý email {i}/{len(eml_files)}: {eml_file.name}")
        
        email_data = extract_email_content(eml_file)
        if not email_data:
            continue
        
        # Tạo text file
        text_filename = f"{i:02d}_{eml_file.stem}.txt"
        text_file_path = texts_folder / text_filename
        
        # Tạo nội dung text file
        text_content = f"""=== EMAIL {i} ===
Subject: {email_data['metadata']['subject']}
From: {email_data['metadata']['sender']}
To: {email_data['metadata']['recipient']}
Date: {email_data['metadata']['date_str']}
Original File: {email_data['metadata']['filename']}

=== CONTENT ===
{email_data['content']['text']}
"""
        
        # Lưu text file
        with open(text_file_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        # Lưu images
        email_images = []
        for img in email_data['images']:
            img_filename = generate_safe_filename(img['filename'], used_filenames)
            img_path = images_folder / img_filename
            
            try:
                with open(img_path, 'wb') as f:
                    f.write(img['content'])
                email_images.append({
                    'original_name': img['filename'],
                    'saved_name': img_filename,
                    'content_type': img['content_type'],
                    'size': img['size']
                })
                thread_data['summary']['total_images'] += 1
            except Exception as e:
                print(f"      Lỗi khi lưu ảnh {img['filename']}: {e}")
        
        # Lưu attachments khác
        email_attachments = []
        for att in email_data['attachments']:
            att_filename = generate_safe_filename(att['filename'], used_filenames)
            att_path = attachments_folder / att_filename
            
            try:
                with open(att_path, 'wb') as f:
                    f.write(att['content'])
                email_attachments.append({
                    'original_name': att['filename'],
                    'saved_name': att_filename,
                    'content_type': att['content_type'],
                    'size': att['size']
                })
                thread_data['summary']['total_attachments'] += 1
            except Exception as e:
                print(f"      Lỗi khi lưu attachment {att['filename']}: {e}")
        
        # Thêm vào thread data
        thread_data['emails'].append({
            'index': i,
            'original_file': email_data['metadata']['filename'],
            'text_file': text_filename,
            'metadata': email_data['metadata'],
            'images': email_images,
            'attachments': email_attachments,
            'text_length': len(email_data['content']['text'])
        })
        
        thread_data['summary']['total_text_length'] += len(email_data['content']['text'])
    
    # Tạo thread summary
    summary_content = f"""=== THREAD SUMMARY ===
Thread Name: {thread_name}
Total Emails: {thread_data['total_emails']}
Total Images: {thread_data['summary']['total_images']}
Total Attachments: {thread_data['summary']['total_attachments']}
Total Text Length: {thread_data['summary']['total_text_length']} characters
Processed Date: {thread_data['processed_date']}

=== EMAIL LIST ===
"""
    
    for email in thread_data['emails']:
        summary_content += f"""
{email['index']:2d}. {email['metadata']['subject']}
    From: {email['metadata']['sender']}
    Date: {email['metadata']['date_str']}
    Text File: {email['text_file']}
    Images: {len(email['images'])}
    Attachments: {len(email['attachments'])}
"""
    
    # Lưu summary
    with open(thread_output / "thread_summary.txt", 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    # Lưu metadata JSON
    with open(thread_output / "metadata.json", 'w', encoding='utf-8') as f:
        json.dump(thread_data, f, indent=2, ensure_ascii=False, default=str)
    
    # Xóa folder rỗng
    if not list(images_folder.iterdir()):
        images_folder.rmdir()
    if not list(attachments_folder.iterdir()):
        attachments_folder.rmdir()
    
    return thread_data

def convert_all_threads(threads_folder, output_folder):
    """
    Chuyển đổi tất cả threads thành định dạng text + images
    """
    threads_folder = Path(threads_folder)
    output_folder = Path(output_folder)
    
    if not threads_folder.exists():
        print(f"Folder không tồn tại: {threads_folder}")
        return
    
    output_folder.mkdir(parents=True, exist_ok=True)
    
    print(f"🔄 Bắt đầu chuyển đổi threads từ: {threads_folder}")
    print(f"📁 Output folder: {output_folder}")
    
    # Lấy danh sách các thread folders
    thread_folders = [f for f in threads_folder.iterdir() if f.is_dir()]
    
    if not thread_folders:
        print("Không tìm thấy thread folder nào!")
        return
    
    print(f"Tìm thấy {len(thread_folders)} threads")
    
    # Thống kê tổng quan
    total_processed = 0
    total_emails = 0
    total_images = 0
    total_attachments = 0
    failed_threads = []
    
    # Xử lý từng thread
    for i, thread_folder in enumerate(thread_folders, 1):
        print(f"\n📂 [{i}/{len(thread_folders)}] Xử lý thread: {thread_folder.name}")
        
        try:
            thread_data = process_single_thread(thread_folder, output_folder)
            
            if thread_data:
                total_processed += 1
                total_emails += thread_data['total_emails']
                total_images += thread_data['summary']['total_images']
                total_attachments += thread_data['summary']['total_attachments']
                
                print(f"   ✅ Hoàn thành: {thread_data['total_emails']} emails, "
                      f"{thread_data['summary']['total_images']} ảnh, "
                      f"{thread_data['summary']['total_attachments']} attachments")
            else:
                failed_threads.append(thread_folder.name)
                print(f"   ❌ Thất bại")
                
        except Exception as e:
            failed_threads.append(thread_folder.name)
            print(f"   ❌ Lỗi: {e}")
    
    # Tạo tổng báo cáo
    report_content = f"""=== CONVERSION REPORT ===
Total Threads Found: {len(thread_folders)}
Successfully Processed: {total_processed}
Failed: {len(failed_threads)}
Total Emails Processed: {total_emails}
Total Images Extracted: {total_images}
Total Attachments Extracted: {total_attachments}
Conversion Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

=== FAILED THREADS ===
{chr(10).join(failed_threads) if failed_threads else 'None'}
"""
    
    with open(output_folder / "conversion_report.txt", 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    print(f"\n✨ HOÀN THÀNH CHUYỂN ĐỔI:")
    print(f"   - Threads xử lý thành công: {total_processed}/{len(thread_folders)}")
    print(f"   - Tổng emails: {total_emails}")
    print(f"   - Tổng ảnh: {total_images}")
    print(f"   - Tổng attachments: {total_attachments}")
    print(f"   - Báo cáo chi tiết: {output_folder / 'conversion_report.txt'}")
    
    if failed_threads:
        print(f"   ⚠️  Threads thất bại: {len(failed_threads)}")

if __name__ == "__main__":
    # Đường dẫn input (threads đã được nhóm)
    threads_folder = r"D:\Project\DATN_HUST\ai-agent\data\eml_threads"
    
    # Đường dẫn output (text + images)
    output_folder = r"D:\Project\DATN_HUST\ai-agent\data\processed_threads"
    
    print("🔄 Bắt đầu chuyển đổi email threads thành text + images...")
    
    # Kiểm tra input folder
    if not Path(threads_folder).exists():
        print(f"❌ Input folder không tồn tại: {threads_folder}")
        print("Vui lòng chạy script group_thread_email.py trước!")
    else:
        # Hỏi xác nhận
        print(f"📂 Input: {threads_folder}")
        print(f"📁 Output: {output_folder}")
        
        choice = input("\nBạn có muốn tiếp tục chuyển đổi? (Enter để tiếp tục, 'n' để hủy): ").strip().lower()
        
        if choice != 'n':
            convert_all_threads(threads_folder, output_folder)
        else:
            print("✅ Đã hủy chuyển đổi.") 