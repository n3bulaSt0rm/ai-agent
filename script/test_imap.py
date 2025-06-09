import json
import time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from imapclient import IMAPClient
from email import message_from_bytes
from email.header import decode_header

TOKEN_PATH = r"D:\Project\DATN_HUST\ai-agent\secret\dev\token.json"

def decode_mime_words(s):
    """Decode MIME encoded-words in headers"""
    if not s:
        return s
    decoded_parts = []
    for part, encoding in decode_header(s):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
        else:
            decoded_parts.append(part)
    return ''.join(decoded_parts)

def process_new_emails(client, last_unseen_uids):
    """Xử lý email mới"""
    try:
        # Lấy danh sách email chưa đọc hiện tại
        current_unseen = set(client.search(['UNSEEN']))
        
        # Tìm email mới (có trong current nhưng không có trong last)
        new_emails = current_unseen - last_unseen_uids
        
        if new_emails:
            print(f"📬 Phát hiện {len(new_emails)} email mới!")
            
            # Sắp xếp theo UID để lấy email mới nhất
            new_emails_sorted = sorted(new_emails)[-3:]  # Chỉ lấy 3 email mới nhất
            
            try:
                # Fetch email details
                inbox_msgs = client.fetch(new_emails_sorted, ['RFC822'])
                
                for msgid, data in inbox_msgs.items():
                    try:
                        msg = message_from_bytes(data[b'RFC822'])
                        
                        # Decode subject và from
                        subject = decode_mime_words(msg.get('Subject', '(No Subject)'))
                        from_addr = decode_mime_words(msg.get('From', '(Unknown Sender)'))
                        
                        print(f"\n📩 [Email mới UID: {msgid}]")
                        print(f"   From: {from_addr}")
                        print(f"   Subject: {subject}")
                        print(f"   Date: {msg.get('Date', 'Unknown')}")
                        
                    except Exception as e:
                        print(f"❌ Lỗi decode email UID {msgid}: {e}")
                        
            except Exception as e:
                print(f"❌ Lỗi fetch email: {e}")
        
        return current_unseen
        
    except Exception as e:
        print(f"❌ Lỗi xử lý email: {e}")
        return last_unseen_uids

def main():
    # Load credentials
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes=["https://mail.google.com/"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    with open(TOKEN_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    email_account = data['account']
    access_token = creds.token

    print(f"🔐 Đã load token cho: {email_account}")

    # Kết nối IMAP
    client = IMAPClient('imap.gmail.com', ssl=True)
    
    try:
        client.oauth2_login(email_account, access_token)
        print("✅ Đã kết nối Gmail IMAP")
        
        # Select INBOX
        select_info = client.select_folder('INBOX')
        print(f"📂 INBOX - Tổng số email: {select_info[b'EXISTS']}")
        
        # Lấy danh sách email chưa đọc ban đầu
        initial_unseen = set(client.search(['UNSEEN']))
        print(f"📧 Hiện tại có {len(initial_unseen)} email chưa đọc")
        
        print("📡 Bắt đầu IDLE monitoring... (Ctrl+C để dừng)")
        
        unseen_uids = initial_unseen
        idle_start_time = time.time()
        
        try:
            while True:
                # Kiểm tra nếu đã IDLE quá 9 phút -> renew
                if time.time() - idle_start_time > 540:  # 9 phút
                    print("🔄 Renew IDLE connection (9 phút)")
                    try:
                        client.idle_done()
                    except:
                        pass
                    time.sleep(0.5)
                    idle_start_time = time.time()
                
                print("⏳ Bắt đầu IDLE...")
                
                # Bắt đầu IDLE
                client.idle()
                
                # Chờ response với timeout ngắn (30 giây)
                try:
                    responses = client.idle_check(timeout=30)
                    
                    if responses:
                        print(f"🔔 IDLE response: {responses}")
                        
                        # Dừng IDLE để kiểm tra email
                        client.idle_done()
                        
                        # Xử lý email mới
                        unseen_uids = process_new_emails(client, unseen_uids)
                        
                        # Reset timer
                        idle_start_time = time.time()
                        
                    else:
                        # Timeout - dừng IDLE và kiểm tra email
                        print("⏰ IDLE timeout 30s")
                        client.idle_done()
                        
                        # Kiểm tra email mới (có thể có email mà server không gửi IDLE response)
                        unseen_uids = process_new_emails(client, unseen_uids)
                        
                        # Reset timer nếu gần hết thời gian
                        if time.time() - idle_start_time > 480:  # 8 phút
                            idle_start_time = time.time()
                
                except Exception as e:
                    print(f"❌ Lỗi IDLE check: {e}")
                    try:
                        client.idle_done()
                    except:
                        pass
                    
                    # Kiểm tra connection
                    try:
                        client.noop()
                        print("🔄 Connection OK, tiếp tục...")
                    except Exception as conn_e:
                        print(f"❌ Mất kết nối: {conn_e}")
                        break
                    
                    # Reset timer
                    idle_start_time = time.time()
                
                # Nghỉ ngắn trước khi IDLE tiếp
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n🛑 Dừng IDLE monitoring")
            try:
                client.idle_done()
            except:
                pass
                
    except Exception as e:
        print(f"❌ Lỗi kết nối IMAP: {e}")
        
    finally:
        try:
            client.logout()
            print("👋 Đã đăng xuất")
        except:
            pass

if __name__ == "__main__":
    main()