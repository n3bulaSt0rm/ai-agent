from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Đường dẫn tới token.json của bạn
token_path = r"D:\Project\DATN_HUST\ai-agent\secret\prod\token.json"

# Khởi tạo credentials từ file token
creds = Credentials.from_authorized_user_file(
    token_path,
    scopes=['https://www.googleapis.com/auth/gmail.readonly']
)

# Khởi tạo service Gmail
service = build('gmail', 'v1', credentials=creds)

# Lấy một email chưa đọc mới nhất trong Inbox
results = service.users().messages().list(
    userId='me',
    labelIds=['INBOX', 'UNREAD'],
    maxResults=1
).execute()

messages = results.get('messages', [])

if not messages:
    print("Không có email chưa đọc.")
else:
    msg_id = messages[0]['id']
    message = service.users().messages().get(
        userId='me',
        id=msg_id,
        format='full'
    ).execute()
    
    # Trích xuất header cần thiết
    headers = message['payload']['headers']
    id = message['id']
    subject = next(h['value'] for h in headers if h['name'] == 'Subject')
    sender = next(h['value'] for h in headers if h['name'] == 'From')
    date = next(h['value'] for h in headers if h['name'] == 'Date')

    print("Email chưa đọc mới nhất:")
    print(f"Từ: {sender}")
    print(f"Chủ đề: {subject}")
    print(f"Ngày: {date}")
    print(f"ID: {id}")