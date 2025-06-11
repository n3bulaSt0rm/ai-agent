import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
import email

# Đường dẫn đến file token
TOKEN_PATH = r"D:\Project\DATN_HUST\ai-agent\secret\prod\token.json"

# Tải credentials
creds = Credentials.from_authorized_user_file(TOKEN_PATH, ['https://www.googleapis.com/auth/gmail.readonly'])

# Khởi tạo Gmail API client
service = build('gmail', 'v1', credentials=creds)

# Thay bằng threadId bạn có
thread_id = '19755b52db9ac903'

# Gọi API lấy thread
thread = service.users().threads().get(userId='me', id=thread_id).execute()

messages = thread.get('messages', [])

print(f"Thread contains {len(messages)} message(s):\n")

# Lặp qua từng email trong thread
for idx, msg in enumerate(messages, start=1):
    msg_id = msg['id']
    headers = msg['payload'].get('headers', [])

    # Trích xuất một số header phổ biến
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
    from_email = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown Sender)')
    date = next((h['value'] for h in headers if h['name'] == 'Date'), '(No Date)')

    # Giải mã nội dung email nếu là text/plain
    parts = msg['payload'].get('parts', [])
    body = ''
    if 'data' in msg['payload'].get('body', {}):
        body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8', errors='ignore')
    elif parts:
        for part in parts:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                break

    print(f"--- Message {idx} ---")
    print(f"ID     : {msg_id}")
    print(f"From   : {from_email}")
    print(f"Date   : {date}")
    print(f"Subject: {subject}")
    print(f"Body   :\n{body[:500]}")  # In 500 ký tự đầu tiên
