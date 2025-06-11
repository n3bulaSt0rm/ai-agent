import os
import re
from email.utils import parsedate_to_datetime
from collections import defaultdict
import email


def create_safe_filename(subject, email_index):
    """Tạo tên file an toàn từ subject, ưu tiên giữ nguyên tên gốc"""
    if not subject or subject.isspace():
        return f"email_{email_index}"
    
    # Chỉ thay thế các ký tự thực sự không hợp lệ cho tên file
    # Giữ lại nhiều ký tự đặc biệt hơn để tránh trùng lặp
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', subject)
    filename = filename.strip()
    
    # Không cắt tên file, để giữ tính unique
    # Nếu tên quá dài, Windows sẽ tự xử lý
    return filename or f"email_{email_index}"


def extract_emails_from_mbox_simple(mbox_file_path, output_dir, filter_from_year=None):
    """Trích xuất email từ mbox - phiên bản đơn giản, chính xác"""
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Đang xử lý file: {mbox_file_path}")
    if filter_from_year:
        print(f"Lọc email từ năm {filter_from_year} trở đi...")
    print("Xử lý tuần tự để đảm bảo độ chính xác...")

    # Counters
    total_scanned = 0
    total_saved = 0
    total_skipped = 0
    total_errors = 0
    year_stats = defaultdict(int)

    print("Bắt đầu đọc file mbox...")

    with open(mbox_file_path, 'r', encoding='utf-8', errors='replace') as f:
        current_email_lines = []
        
        for line_num, line in enumerate(f, 1):
            # Dòng bắt đầu email mới
            if line.startswith('From ') and current_email_lines:
                # Xử lý email hiện tại với chỉ số chính xác
                result = process_single_email_simple(
                    current_email_lines, output_dir, total_scanned + 1, filter_from_year
                )
                
                total_scanned += 1
                
                if result['status'] == 'SAVED':
                    total_saved += 1
                elif result['status'] == 'SKIPPED':
                    total_skipped += 1
                elif result['status'] == 'ERROR':
                    total_errors += 1
                
                if result['year']:
                    year_stats[result['year']] += 1
                
                # In tiến độ mỗi 100 email
                if total_scanned % 100 == 0:
                    print(f"Đã quét: {total_scanned} | Lưu: {total_saved} | Bỏ qua: {total_skipped} | Lỗi: {total_errors}")
                
                # Reset cho email tiếp theo
                current_email_lines = [line]
            else:
                current_email_lines.append(line)
        
        # Xử lý email cuối cùng
        if current_email_lines:
            result = process_single_email_simple(
                current_email_lines, output_dir, total_scanned + 1, filter_from_year
            )
            
            total_scanned += 1
            
            if result['status'] == 'SAVED':
                total_saved += 1
            elif result['status'] == 'SKIPPED':
                total_skipped += 1
            elif result['status'] == 'ERROR':
                total_errors += 1
            
            if result['year']:
                year_stats[result['year']] += 1

    # Kiểm tra số file thực tế
    actual_files = [f for f in os.listdir(output_dir) if f.endswith('.eml')]
    actual_count = len(actual_files)

    # In kết quả
    print(f"\n=== THỐNG KÊ THEO NĂM ===")
    if year_stats:
        sorted_years = sorted(year_stats.items())
        for year, count in sorted_years:
            print(f"Năm {year}: {count} emails")
    else:
        print("Không có thông tin năm từ các email")

    print(f"\n=== KẾT QUẢ CUỐI CÙNG ===")
    print(f"Tổng số email đã quét: {total_scanned}")
    print(f"Số email đã lưu (counter): {total_saved}")
    print(f"Số email bỏ qua: {total_skipped}")
    print(f"Số email lỗi: {total_errors}")
    print(f"Số file .eml thực tế: {actual_count}")
    
    # Kiểm tra tính nhất quán
    if actual_count == total_saved:
        print("✅ Counter và số file thực tế khớp nhau!")
    else:
        print(f"⚠️  CẢNH BÁO: Counter ({total_saved}) != Số file thực tế ({actual_count})")
        difference = actual_count - total_saved
        if difference > 0:
            print(f"   Có {difference} file thừa - có thể từ lần chạy trước")
        else:
            print(f"   Thiếu {abs(difference)} file - có lỗi trong quá trình lưu")


def process_single_email_simple(email_lines, output_dir, email_index, filter_year):
    """Xử lý một email đơn lẻ - phiên bản đơn giản"""
    
    try:
        # Ghép nội dung email
        email_content = ''.join(email_lines)
        
        # Parse email
        message = email.message_from_string(email_content)
        
        # Lấy thông tin ngày tháng
        date_str = message.get('Date', '')
        email_year = None
        
        if date_str:
            try:
                date_obj = parsedate_to_datetime(date_str)
                if date_obj:
                    email_year = date_obj.year
                    
                    # Kiểm tra filter năm
                    if filter_year and email_year < filter_year:
                        return {
                            'status': 'SKIPPED',
                            'year': email_year,
                            'message': f'Bỏ qua email năm {email_year}'
                        }
            except Exception as e:
                # Không parse được date, vẫn tiếp tục xử lý
                pass
        
        # Lấy subject
        subject = message.get('Subject', '')
        
        # Decode subject nếu cần
        if subject:
            try:
                from email.header import decode_header
                decoded_parts = decode_header(subject)
                subject_parts = []
                
                for part, encoding in decoded_parts:
                    if isinstance(part, bytes):
                        if encoding:
                            try:
                                subject_parts.append(part.decode(encoding, errors='replace'))
                            except:
                                subject_parts.append(part.decode('utf-8', errors='replace'))
                        else:
                            subject_parts.append(part.decode('utf-8', errors='replace'))
                    else:
                        subject_parts.append(str(part))
                
                subject = ''.join(subject_parts)
            except Exception as e:
                # Nếu decode lỗi, giữ nguyên subject gốc
                pass
        
        # Tạo tên file với prefix index để đảm bảo unique
        safe_subject = create_safe_filename(subject, email_index)
        filename = f"{email_index:06d}_{safe_subject}.eml"
        
        # Nếu tên file quá dài, cắt phần subject
        if len(filename) > 255:  # Windows file name limit
            max_subject_len = 255 - 11  # 11 = "000000_" + ".eml"
            safe_subject = safe_subject[:max_subject_len]
            filename = f"{email_index:06d}_{safe_subject}.eml"
        
        file_path = os.path.join(output_dir, filename)
        
        # Với prefix index, không cần lo trùng tên nữa
        # Nhưng vẫn kiểm tra để đảm bảo
        if os.path.exists(file_path):
            filename = f"{email_index:06d}_duplicate_{safe_subject}.eml"
            file_path = os.path.join(output_dir, filename)
        
        # Lưu file
        with open(file_path, 'w', encoding='utf-8', errors='replace') as f:
            f.write(email_content)
        
        return {
            'status': 'SAVED',
            'year': email_year,
            'message': f'Đã lưu: {filename}'
        }
        
    except Exception as e:
        # Lưu email với tên lỗi
        error_filename = f"{email_index:06d}_error.eml"
        error_path = os.path.join(output_dir, error_filename)
        
        try:
            email_content = ''.join(email_lines)
            with open(error_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(email_content)
            
            return {
                'status': 'SAVED',  # Vẫn được lưu nhưng với tên lỗi
                'year': None,
                'message': f'Lưu với lỗi: {error_filename} - {str(e)}'
            }
        except:
            return {
                'status': 'ERROR',
                'year': None,
                'message': f'Không thể lưu email {email_index}: {str(e)}'
            }


def get_mbox_info_simple(mbox_file_path):
    """Hiển thị thông tin file mbox - phiên bản đơn giản"""
    
    print(f"=== THÔNG TIN FILE MBOX ===")
    print(f"Đường dẫn: {mbox_file_path}")
    
    try:
        file_size = os.path.getsize(mbox_file_path)
        print(f"Kích thước file: {file_size / (1024 * 1024 * 1024):.2f} GB")
    except:
        print("Không thể lấy kích thước file")
    
    print("Đang đếm số email...")
    
    email_count = 0
    sample_emails = []
    year_preview = defaultdict(int)
    
    try:
        with open(mbox_file_path, 'r', encoding='utf-8', errors='replace') as f:
            current_email = []
            
            for line in f:
                if line.startswith('From ') and current_email:
                    email_count += 1
                    
                    # Lấy mẫu từ 10 email đầu
                    if len(sample_emails) < 5:
                        try:
                            email_content = ''.join(current_email)
                            message = email.message_from_string(email_content)
                            
                            subject = message.get('Subject', 'No Subject')
                            sender = message.get('From', 'Unknown')
                            date_str = message.get('Date', 'Unknown Date')
                            
                            sample_emails.append({
                                'subject': subject[:100] + '...' if len(subject) > 100 else subject,
                                'sender': sender[:50] + '...' if len(sender) > 50 else sender,
                                'date': date_str
                            })
                            
                            # Thống kê năm
                            if date_str != 'Unknown Date':
                                try:
                                    date_obj = parsedate_to_datetime(date_str)
                                    if date_obj:
                                        year_preview[date_obj.year] += 1
                                except:
                                    pass
                        except:
                            pass
                    
                    current_email = [line]
                    
                    # Hiển thị tiến độ
                    if email_count % 1000 == 0:
                        print(f"Đang đếm... {email_count} emails")
                
                else:
                    current_email.append(line)
            
            # Email cuối cùng
            if current_email:
                email_count += 1
        
        print(f"Tổng số email: {email_count}")
        
        # Hiển thị mẫu email
        if sample_emails:
            print(f"\n=== MẪU EMAIL ===")
            for i, email_info in enumerate(sample_emails):
                print(f"Email {i + 1}:")
                print(f"  From: {email_info['sender']}")
                print(f"  Subject: {email_info['subject']}")
                print(f"  Date: {email_info['date']}")
                print()
        
        # Hiển thị preview năm
        if year_preview:
            print(f"=== PREVIEW THỐNG KÊ NĂM ===")
            sorted_years = sorted(year_preview.items())
            for year, count in sorted_years:
                print(f"Năm {year}: {count} emails (từ mẫu)")
    
    except Exception as e:
        print(f"Lỗi khi đọc file: {e}")


if __name__ == "__main__":
    mbox_file = r"D:\Project\DATN_HUST\ai-agent\data\All mail Including Spam and Trash"  
    output_directory = r"D:\Project\DATN_HUST\ai-agent\data\eml"  
    filter_year = 2022

    if not os.path.exists(mbox_file):
        print(f"File không tồn tại: {mbox_file}")
        print("Vui lòng cập nhật đường dẫn đến file mbox của bạn")
    else:
        # Hiển thị thông tin file mbox
        get_mbox_info_simple(mbox_file)
        
        print(f"\n{'='*50}")
        print("BẮT ĐẦU TRÍCH XUẤT EMAIL")
        if filter_year:
            print(f"Chỉ trích xuất email từ năm {filter_year} trở đi")
        else:
            print("Trích xuất TẤT CẢ email (không lọc theo năm)")
        print(f"{'='*50}")
        
        import time
        start_time = time.time()
        
        extract_emails_from_mbox_simple(mbox_file, output_directory, filter_year)
        
        end_time = time.time()
        print(f"\nThời gian xử lý: {end_time - start_time:.1f} giây")