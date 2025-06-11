import os.path
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Load credentials from token file
TOKEN_PATH = r"D:\Project\DATN_HUST\ai-agent\secret\prod\token.json"
creds = Credentials.from_authorized_user_file(TOKEN_PATH, ['https://www.googleapis.com/auth/gmail.modify'])

# Build Gmail API service
service = build('gmail', 'v1', credentials=creds)

# Thread ID bạn đã có
thread_id = '19755b52db9ac903'  # <- thay bằng threadId thật của bạn

# Nội dung email draft
to = "tunghahaha1999@gmail.com"
subject = "Draft reply for existing thread"
body = "This is a draft email reply for an existing thread."

# Tạo MIME message
message = MIMEText(body)
message['to'] = to
message['subject'] = subject

# Encode message thành base64
raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

# Tạo draft gắn với thread
create_draft_request = {
    'message': {
        'raw': raw_message,
        'threadId': thread_id  # gắn draft vào thread này
    }
}

# Gửi yêu cầu tạo draft
draft = service.users().drafts().create(userId='me', body=create_draft_request).execute()
print(f"Draft ID: {draft['id']} created in thread {thread_id}")
