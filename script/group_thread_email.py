import os
import email
from email import policy
from email.utils import parsedate_to_datetime
from collections import defaultdict
import re
from pathlib import Path
import shutil
from datetime import datetime

def extract_thread_identifiers(msg):
    """
    Trích xuất các thông tin để xác định thread email
    """
    # Message-ID của email hiện tại
    message_id = msg.get('Message-ID', '').strip('<>')
    
    # In-Reply-To header (email mà email này reply)
    in_reply_to = msg.get('In-Reply-To', '').strip('<>')
    
    # References header (chuỗi tất cả message-id trong thread)
    references = msg.get('References', '')
    reference_ids = []
    if references:
        # Tách các message-id từ References header
        reference_ids = re.findall(r'<([^>]+)>', references)
    
    # Subject (loại bỏ Re:, Fwd: để so sánh)
    subject = msg.get('Subject', '')
    clean_subject = re.sub(r'^(Re:|RE:|Fwd:|FWD:|Fw:|FW:)\s*', '', subject, flags=re.IGNORECASE).strip()
    
    # Parse date cho việc sắp xếp
    date_str = msg.get('Date', '')
    parsed_date = None
    if date_str:
        try:
            parsed_date = parsedate_to_datetime(date_str)
        except:
            pass
    
    return {
        'message_id': message_id,
        'in_reply_to': in_reply_to,
        'references': reference_ids,
        'subject': clean_subject,
        'original_subject': subject,
        'date_str': date_str,
        'parsed_date': parsed_date
    }

def find_email_threads(folder_path):
    """
    Tìm và nhóm các email cùng thread - cải thiện algorithm
    """
    folder_path = Path(folder_path)
    
    if not folder_path.exists():
        print(f"Folder không tồn tại: {folder_path}")
        return {}
    
    # Dictionary để lưu thông tin các email
    emails_info = {}
    
    # Đọc tất cả file .eml
    eml_files = list(folder_path.glob("*.eml"))
    print(f"Tìm thấy {len(eml_files)} file .eml")
    
    for eml_file in eml_files:
        try:
            with open(eml_file, 'rb') as f:
                msg = email.message_from_bytes(f.read(), policy=policy.default)
                
            thread_info = extract_thread_identifiers(msg)
            thread_info['filename'] = eml_file.name
            thread_info['filepath'] = str(eml_file)
            
            emails_info[eml_file.name] = thread_info
            
        except Exception as e:
            print(f"Lỗi khi đọc file {eml_file.name}: {e}")
    
    print(f"Đã đọc thành công {len(emails_info)} email")
    
    # Thuật toán nhóm thread cải thiện
    return group_emails_by_thread(emails_info)

def group_emails_by_thread(emails_info):
    """
    Nhóm email theo thread sử dụng thuật toán Union-Find cải thiện
    """
    # Tạo mapping từ message-id đến filename
    msgid_to_file = {}
    for filename, info in emails_info.items():
        if info['message_id']:
            msgid_to_file[info['message_id']] = filename
    
    # Union-Find để nhóm email
    parent = {}
    
    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    
    # Khởi tạo: mỗi email là một nhóm riêng
    for filename in emails_info:
        parent[filename] = filename
    
    # Nhóm email dựa trên In-Reply-To và References
    for filename, info in emails_info.items():
        # Nối với email mà nó reply
        if info['in_reply_to'] and info['in_reply_to'] in msgid_to_file:
            related_file = msgid_to_file[info['in_reply_to']]
            union(filename, related_file)
        
        # Nối với các email trong References
        for ref_id in info['references']:
            if ref_id in msgid_to_file:
                related_file = msgid_to_file[ref_id]
                union(filename, related_file)
    
    # Nhóm theo subject cho các email không có message-id relationships
    subject_groups = defaultdict(list)
    for filename, info in emails_info.items():
        if info['subject']:
            subject_groups[info['subject'].lower()].append(filename)
    
    # Nối các email có cùng subject (chỉ khi không có message-id relationship)
    for subject, files in subject_groups.items():
        if len(files) > 1:
            # Kiểm tra xem các file này đã được nhóm chưa
            representatives = set(find(f) for f in files)
            if len(representatives) == len(files):  # Chưa được nhóm
                # Chỉ nhóm nếu time stamp gần nhau (trong vòng 30 ngày)
                dates = []
                for f in files:
                    if emails_info[f]['parsed_date']:
                        dates.append(emails_info[f]['parsed_date'])
                
                if len(dates) > 1:
                    dates.sort()
                    time_diff = (dates[-1] - dates[0]).days
                    if time_diff <= 30:  # Trong vòng 30 ngày
                        for i in range(1, len(files)):
                            union(files[0], files[i])
    
    # Tạo các nhóm thread cuối cùng
    threads = defaultdict(list)
    for filename in emails_info:
        root = find(filename)
        threads[root].append(emails_info[filename])
    
    # Sắp xếp email trong mỗi thread theo thời gian
    for thread_id in threads:
        threads[thread_id].sort(key=lambda x: x['parsed_date'] or datetime.min)
    
    return dict(threads)

def find_related_emails(current_email, all_emails, processed):
    """
    Tìm các email liên quan đến email hiện tại - deprecated, dùng group_emails_by_thread thay thế
    """
    # Function này không còn được sử dụng trong algorithm mới
    return []

def sanitize_folder_name(name):
    """
    Làm sạch tên folder để có thể tạo folder trên hệ thống
    """
    # Thay thế các ký tự không hợp lệ
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    
    # Thay thế nhiều dấu gạch dưới liên tiếp bằng một dấu
    name = re.sub(r'_+', '_', name)
    
    # Giới hạn độ dài
    if len(name) > 80:
        name = name[:80]
    
    # Loại bỏ khoảng trắng đầu/cuối và dấu gạch dưới
    name = name.strip('_ ')
    
    # Đảm bảo không rỗng
    if not name:
        name = "unnamed_thread"
    
    return name

def export_threads_to_folders(threads, output_folder):
    """
    Xuất các email threads vào các folder riêng biệt
    """
    output_path = Path(output_folder)
    
    # Tạo folder output nếu chưa tồn tại
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📁 Bắt đầu xuất threads vào folder: {output_path}")
    
    exported_threads = 0
    exported_emails = 0
    single_emails_folder = None
    
    # Sắp xếp threads theo số lượng email (thread có nhiều email trước)
    sorted_threads = sorted(threads.items(), key=lambda x: len(x[1]), reverse=True)
    
    for thread_id, emails in sorted_threads:
        if len(emails) == 1:
            # Xử lý email đơn lẻ - tạo folder "single_emails" chung
            if single_emails_folder is None:
                single_emails_folder = output_path / "single_emails"
                single_emails_folder.mkdir(exist_ok=True)
                print(f"   📂 Tạo folder cho email đơn lẻ: {single_emails_folder.name}")
            
            # Copy email đơn lẻ
            email_info = emails[0]
            source_file = Path(email_info['filepath'])
            dest_file = single_emails_folder / email_info['filename']
            
            try:
                shutil.copy2(source_file, dest_file)
                exported_emails += 1
            except Exception as e:
                print(f"   ❌ Lỗi khi copy {email_info['filename']}: {e}")
        else:
            # Xử lý thread có nhiều email
            # Tạo tên folder từ subject của email đầu tiên (theo thời gian)
            first_email = emails[0]  # Đã được sắp xếp theo thời gian
            
            if first_email['subject']:
                folder_name = f"thread_{len(emails)}_{sanitize_folder_name(first_email['subject'])}"
            else:
                folder_name = f"thread_{len(emails)}_unnamed"
            
            thread_folder = output_path / folder_name
            
            # Xử lý trường hợp folder đã tồn tại
            counter = 1
            original_folder_name = folder_name
            while thread_folder.exists():
                folder_name = f"{original_folder_name}_{counter}"
                thread_folder = output_path / folder_name
                counter += 1
            
            # Tạo folder cho thread
            thread_folder.mkdir(exist_ok=True)
            print(f"   📂 Thread với {len(emails)} emails: {thread_folder.name}")
            
            # Copy các email trong thread (đã sắp xếp theo thời gian)
            thread_exported = 0
            for i, email_info in enumerate(emails, 1):
                source_file = Path(email_info['filepath'])
                
                # Thêm prefix số thứ tự cho file
                original_name = email_info['filename']
                if original_name.endswith('.eml'):
                    new_name = f"{i:02d}_{original_name}"
                else:
                    new_name = f"{i:02d}_{original_name}.eml"
                
                dest_file = thread_folder / new_name
                
                try:
                    shutil.copy2(source_file, dest_file)
                    thread_exported += 1
                    exported_emails += 1
                except Exception as e:
                    print(f"   ❌ Lỗi khi copy {email_info['filename']}: {e}")
            
            print(f"      ✅ Đã copy {thread_exported}/{len(emails)} email")
            exported_threads += 1
    
    print(f"\n✨ HOÀN THÀNH XUẤT DỮ LIỆU:")
    print(f"   - Tổng số email đã xuất: {exported_emails}")
    print(f"   - Số threads đã xuất: {exported_threads}")
    if single_emails_folder:
        single_count = len(list(single_emails_folder.glob("*.eml")))
        print(f"   - Email đơn lẻ: {single_count}")
    print(f"   - Folder output: {output_path}")

def print_thread_analysis(threads):
    """
    In kết quả phân tích thread
    """
    print("\n" + "="*80)
    print("KẾT QUẢ PHÂN TÍCH EMAIL THREADS")
    print("="*80)
    
    single_emails = 0
    thread_emails = 0
    
    # Sắp xếp threads theo số lượng email
    sorted_threads = sorted(threads.items(), key=lambda x: len(x[1]), reverse=True)
    
    for thread_id, emails in sorted_threads:
        if len(emails) == 1:
            single_emails += 1
        else:
            thread_emails += len(emails)
            print(f"\n📧 THREAD với {len(emails)} emails:")
            
            # Hiển thị thông tin thread
            first_email = emails[0]
            print(f"   Subject gốc: {first_email['original_subject']}")
            print(f"   Thời gian: {first_email['date_str']}")
            
            # Hiển thị các email trong thread
            for i, email in enumerate(emails, 1):
                print(f"   {i:2d}. {email['filename']}")
                if email['date_str']:
                    print(f"       📅 {email['date_str']}")
                if email['original_subject'] != first_email['original_subject']:
                    print(f"       📧 {email['original_subject']}")
            print()
    
    print(f"\n📊 TỔNG KẾT:")
    print(f"   - Tổng số email: {single_emails + thread_emails}")
    print(f"   - Email đơn lẻ: {single_emails}")
    print(f"   - Email trong threads: {thread_emails}")
    print(f"   - Số threads (có ≥2 email): {len([t for t in threads.values() if len(t) > 1])}")
    
    # Thống kê thread size
    thread_sizes = [len(emails) for emails in threads.values() if len(emails) > 1]
    if thread_sizes:
        print(f"   - Thread lớn nhất: {max(thread_sizes)} emails")
        print(f"   - Thread nhỏ nhất: {min(thread_sizes)} emails")
        print(f"   - Trung bình emails/thread: {sum(thread_sizes)/len(thread_sizes):.1f}")

# Sử dụng
if __name__ == "__main__":
    # Đường dẫn folder chứa file .eml
    input_folder = r"D:\Project\DATN_HUST\ai-agent\data\eml"
    
    # Đường dẫn folder output
    output_folder = r"D:\Project\DATN_HUST\ai-agent\data\eml_threads"
    
    print("🔍 Bắt đầu phân tích email threads...")
    threads = find_email_threads(input_folder)
    
    if threads:
        # In kết quả phân tích
        print_thread_analysis(threads)
        
        # Hỏi người dùng có muốn xuất không
        print(f"\n❓ Bạn có muốn xuất threads vào folder '{output_folder}'?")
        choice = input("Nhấn Enter để tiếp tục, hoặc 'n' để bỏ qua: ").strip().lower()
        
        if choice != 'n':
            # Xuất threads vào các folder
            export_threads_to_folders(threads, output_folder)
        else:
            print("✅ Chỉ phân tích, không xuất file.")
    else:
        print("❌ Không tìm thấy email nào hoặc có lỗi xảy ra.")