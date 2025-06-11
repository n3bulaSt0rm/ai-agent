import mailbox
import os
import re
from email.utils import parsedate_to_datetime
from datetime import datetime
import threading
from queue import Queue
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

def process_single_email(args):
    """Xử lý một email đơn lẻ - để sử dụng với multiprocessing"""
    email_data, output_dir, i, filter_year = args

    try:
        # Parse lại message từ raw data
        import email
        message = email.message_from_string(email_data)

        # Kiểm tra năm gửi email
        date_str = message.get('Date', '')
        email_year = None

        if date_str:
            try:
                date_obj = parsedate_to_datetime(date_str)
                email_year = date_obj.year
                if filter_year and email_year < filter_year:
                    return f"⏭ Email {i} bỏ qua (năm {email_year})", email_year, False
            except:
                # Nếu không parse được date, vẫn xử lý email
                pass

        # Lấy thông tin email
        subject = message.get('Subject', f'No_Subject_{i}')

        # Decode subject nếu cần
        if subject:
            try:
                from email.header import decode_header
                decoded_parts = decode_header(subject)
                subject_parts = []
                for part, encoding in decoded_parts:
                    if isinstance(part, bytes):
                        if encoding:
                            subject_parts.append(part.decode(encoding, errors='replace'))
                        else:
                            subject_parts.append(part.decode('utf-8', errors='replace'))
                    else:
                        subject_parts.append(str(part))
                subject = ''.join(subject_parts)
            except:
                pass

        # Tạo tên file
        filename = f"{subject}.eml"
        file_path = os.path.join(output_dir, filename)

        # Xử lý trường hợp trùng tên file
        counter = 1
        original_filename = filename
        while os.path.exists(file_path):
            name, ext = os.path.splitext(original_filename)
            filename = f"{name}_{counter}{ext}"
            file_path = os.path.join(output_dir, filename)
            counter += 1

        # Lưu email với buffer size lớn hơn
        with open(file_path, 'w', encoding='utf-8', errors='replace', buffering=8192) as f:
            f.write(email_data)

        return f"✓ {filename}", email_year, True

    except Exception as e:
        # Lưu email với tên đơn giản nếu có lỗi
        fallback_filename = f"email_error_{i}.eml"
        fallback_path = os.path.join(output_dir, fallback_filename)
        try:
            with open(fallback_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(email_data)
            return f"⚠ {fallback_filename} (có lỗi: {str(e)})", None, True
        except:
            return f"✗ Không thể lưu email {i}", None, False


def extract_emails_from_mbox_fast(mbox_file_path, output_dir, max_workers=4, filter_from_year=None):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Đang xử lý file: {mbox_file_path}")
    if filter_from_year:
        print(f"Lọc email từ năm {filter_from_year} trở đi...")
    print(f"Sử dụng {max_workers} threads để xử lý song song...")

    start_time = time.time()
    processed_count = 0
    filtered_count = 0
    year_stats = defaultdict(int)  

    with open(mbox_file_path, 'r', encoding='utf-8', errors='replace', buffering=1024 * 1024) as f:
        # Parse từng email một cách streaming
        current_email = []
        email_tasks = []

        for line_num, line in enumerate(f):
            # Dòng bắt đầu email mới trong mbox format
            if line.startswith('From ') and current_email:
                # Xử lý email hiện tại
                email_content = ''.join(current_email)
                email_tasks.append((email_content, output_dir, processed_count, filter_from_year))
                current_email = [line]
                processed_count += 1

                # Xử lý batch để tránh quá tải memory
                if len(email_tasks) >= 50:  # Batch size
                    batch_results = process_batch(email_tasks, max_workers)

                    # Đếm số email được lọc và cập nhật thống kê năm
                    for result in batch_results:
                        if result and len(result) >= 3:
                            message, email_year, saved = result
                            if saved and message.startswith('✓'):
                                filtered_count += 1
                            if email_year:
                                year_stats[email_year] += 1

                    email_tasks = []

                    # Hiển thị tiến độ
                    elapsed = time.time() - start_time
                    speed = processed_count / elapsed if elapsed > 0 else 0
                    print(
                        f"Đã quét: {processed_count} | Đã lưu: {filtered_count} emails | Tốc độ: {speed:.1f} emails/s")

            else:
                current_email.append(line)

        # Xử lý email cuối cùng
        if current_email:
            email_content = ''.join(current_email)
            email_tasks.append((email_content, output_dir, processed_count, filter_from_year))
            processed_count += 1

        # Xử lý batch cuối cùng
        if email_tasks:
            batch_results = process_batch(email_tasks, max_workers)
            for result in batch_results:
                if result and len(result) >= 3:
                    message, email_year, saved = result
                    if saved and message.startswith('✓'):
                        filtered_count += 1
                    if email_year:
                        year_stats[email_year] += 1

    total_time = time.time() - start_time

    print(f"\n=== THỐNG KÊ THEO NĂM ===")
    if year_stats:
        # Sắp xếp theo năm
        sorted_years = sorted(year_stats.items())
        for year, count in sorted_years:
            print(f"Năm {year}: {count} emails")
    else:
        print("Không có thông tin năm từ các email")

    print(f"\n=== HOÀN THÀNH ===")
    print(f"Tổng số email đã quét: {processed_count}")
    print(f"Số email đã lưu: {filtered_count}")
    if filter_from_year:
        print(f"Đã bỏ qua: {processed_count - filtered_count} emails (trước năm {filter_from_year})")
    print(f"Thời gian: {total_time:.1f} giây")
    print(f"Tốc độ quét: {processed_count / total_time:.1f} emails/giây")


def process_batch(email_tasks, max_workers):
    """Xử lý một batch email với ThreadPoolExecutor"""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_email, task) for task in email_tasks]

        for future in as_completed(futures):
            try:
                result = future.result(timeout=30)  # Timeout 30s cho mỗi email
                results.append(result)
                # In kết quả nếu cần debug
                # print(result)
            except Exception as e:
                print(f"Lỗi xử lý batch: {e}")
                results.append((None, None, False))

    return results


def get_mbox_info_fast(mbox_file_path):
    """Hiển thị thông tin tổng quan về file mbox (phiên bản nhanh)"""
    print(f"=== THÔNG TIN FILE MBOX ===")
    print(f"Đường dẫn: {mbox_file_path}")

    # Đếm số email bằng cách đọc streaming
    email_count = 0
    file_size = os.path.getsize(mbox_file_path)
    print(f"Kích thước file: {file_size / (1024 * 1024 * 1024):.2f} GB")

    sample_emails = []
    year_preview = defaultdict(int)  # Thống kê nhanh để xem trước

    with open(mbox_file_path, 'r', encoding='utf-8', errors='replace', buffering=1024 * 1024) as f:
        current_email = []

        for line in f:
            if line.startswith('From ') and current_email:
                email_count += 1

                # Lưu 5 email đầu làm mẫu và thống kê năm
                if len(sample_emails) < 5 or len(year_preview) < 50:  # Lấy mẫu 50 email đầu để thống kê năm
                    try:
                        import email
                        email_content = ''.join(current_email)
                        message = email.message_from_string(email_content)

                        subject = message.get('Subject', 'No Subject')
                        sender = message.get('From', 'Unknown')
                        date_str = message.get('Date', 'Unknown Date')

                        # Thống kê năm
                        if date_str != 'Unknown Date':
                            try:
                                from email.utils import parsedate_to_datetime
                                date_obj = parsedate_to_datetime(date_str)
                                if date_obj:
                                    year_preview[date_obj.year] += 1
                            except:
                                pass

                        if len(sample_emails) < 5:
                            sample_emails.append({
                                'subject': subject,
                                'sender': sender,
                                'date': date_str
                            })
                    except:
                        pass

                current_email = [line]

                # Hiện tiến độ mỗi 1000 email để người dùng biết đang chạy
                if email_count % 1000 == 0:
                    print(f"Đang đếm... {email_count} emails")

            else:
                current_email.append(line)

        # Email cuối cùng
        if current_email:
            email_count += 1

    print(f"Tổng số email: {email_count}")

    # Hiển thị preview thống kê năm (từ mẫu)
    if year_preview:
        print(f"\n=== PREVIEW THỐNG KÊ NĂM (từ {sum(year_preview.values())} email mẫu) ===")
        sorted_years = sorted(year_preview.items())
        for year, count in sorted_years:
            print(f"Năm {year}: {count} emails (mẫu)")

    # Hiển thị mẫu email
    print(f"\n=== MẪU EMAIL ===")
    for i, email_info in enumerate(sample_emails):
        print(f"Email {i + 1}:")
        print(f"  From: {email_info['sender']}")
        print(f"  Subject: {email_info['subject']}")
        print(f"  Date: {email_info['date']}")
        print()


if __name__ == "__main__":
    mbox_file = r"D:\Project\DATN_HUST\ai-agent\data\All mail Including Spam and Trash"  
    output_directory = r"D:\Project\DATN_HUST\ai-agent\data\eml"  

    num_threads = 14 
    filter_year = 2021

    if not os.path.exists(mbox_file):
        print(f"File không tồn tại: {mbox_file}")
        print("Vui lòng cập nhật đường dẫn đến file mbox của bạn")
    else:
        # Hiển thị thông tin file mbox (nhanh)
        get_mbox_info_fast(mbox_file)


        extract_emails_from_mbox_fast(mbox_file, output_directory, num_threads, filter_year)
