import asyncio
import logging
import json
import os
import sys
from typing import Dict, Any, List, Optional

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.services.processing.rag.handler import GmailHandler
from backend.common.config import settings
from backend.services.processing.rag.common.utils import KNOWLEDGE_SUMMARY_SEPARATOR

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Ensure Google API Key is set
if not settings.GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is not set in the environment or .env file.")

# Mock Gmail email address for testing
if not settings.GMAIL_EMAIL_ADDRESS:
    settings.GMAIL_EMAIL_ADDRESS = "phong.ctsv@test.edu.vn"
    logging.warning(f"settings.GMAIL_EMAIL_ADDRESS not set, using mock value: {settings.GMAIL_EMAIL_ADDRESS}")


# --- Test Cases ---

TEST_CASES = [
    {
        "test_name": "Case 1: New thread with a simple, direct question from a student",
        "description": "Tests the basic flow: identifying a clear question and creating initial summaries.",
        "thread_emails": [
            {
                'from': 'student.a@email.com',
                'to': settings.GMAIL_EMAIL_ADDRESS,
                'subject': 'Hỏi về thủ tục miễn giảm học phí',
                'date': '2024-08-01T10:00:00Z',
                'content': 'Dạ em chào phòng CTSV, cho em hỏi thủ tục để xin miễn giảm học phí cho đối tượng hộ nghèo gồm những giấy tờ gì ạ?',
                'attachments': []
            }
        ],
        "existing_summary": None,
    },
    {
        "test_name": "Case 2: New thread with an implicit question and file attachment",
        "description": "Tests the ability to convert a vague request into a specific, actionable question and use attachment context.",
        "thread_emails": [
            {
                'from': 'student.b@email.com',
                'to': settings.GMAIL_EMAIL_ADDRESS,
                'subject': 'Về việc đăng ký môn học trễ hạn',
                'date': '2024-08-02T14:30:00Z',
                'content': 'Kính gửi phòng CTSV, do em bị ốm nặng tuần trước, em đã không kịp đăng ký môn học cho học kỳ này. Em có đính kèm giấy nhập viện. Em có thể làm gì để được nhà trường xem xét ạ? Em cảm ơn.',
                'attachments': []
            }
        ],
        "existing_summary": None,
    },
    {
        "test_name": "Case 3: Update thread - Staff provides knowledge and asks a clarifying question",
        "description": "This is a key test. It checks if the system correctly extracts knowledge from the staff's reply while also recognizing the conversation is ongoing.",
        "existing_summary": f"Sinh viên Nguyễn Văn C hỏi về thủ tục xin hoãn thi.{KNOWLEDGE_SUMMARY_SEPARATOR}Chưa có tri thức.",
        "thread_emails": [
            {
                'from': settings.GMAIL_EMAIL_ADDRESS,
                'to': 'student.c@email.com',
                'subject': 'Re: Thủ tục xin hoãn thi',
                'date': '2024-08-03T11:00:00Z',
                'content': 'Chào em, Về việc hoãn thi, em cần nộp đơn xin hoãn thi kèm theo minh chứng lý do. Tuy nhiên, để hướng dẫn chính xác, em cho phòng biết lý do em xin hoãn là gì nhé (trùng lịch, sức khỏe, hay lý do khác)? Thân,',
                'attachments': []
            }
        ],
    },
    {
        "test_name": "Case 4: Update thread - Staff provides a correction to previous information",
        "description": "Tests the critical ability to update existing knowledge, ensuring incorrect information is replaced by the correct version.",
        "existing_summary": f"Phòng CTSV đã hướng dẫn sinh viên về thủ tục học bổng hè.{KNOWLEDGE_SUMMARY_SEPARATOR}Để nhận học bổng hè, sinh viên cần nộp hồ sơ tại phòng A1-101 trước ngày 15/08/2024.",
        "thread_emails": [
             {
                'from': settings.GMAIL_EMAIL_ADDRESS,
                'to': 'student.d@email.com',
                'subject': 'Re: Đính chính thông tin học bổng hè',
                'date': '2024-08-05T09:00:00Z',
                'content': 'Chào các em, Phòng CTSV xin đính chính, hạn chót nộp hồ sơ học bổng hè là ngày 20/08/2024 (không phải 15/08). Địa điểm nộp vẫn ở A1-101. Mong các em thông cảm và cập nhật. Trân trọng.',
                'attachments': []
            }
        ],
    },
    {
        "test_name": "Case 5: Update thread - Conversation with back-and-forth, knowledge built progressively",
        "description": "A realistic, multi-turn scenario. The final knowledge summary should be a coherent synthesis of all staff replies, not just the last one.",
        "existing_summary": f"Sinh viên Lê Thị E hỏi về học bổng XYZ và đã được hướng dẫn về điều kiện GPA và điểm rèn luyện.{KNOWLEDGE_SUMMARY_SEPARATOR}Điều kiện nhận học bổng XYZ: GPA >= 3.2, Điểm rèn luyện >= 80.",
        "thread_emails": [
            {
                'from': 'student.e@email.com',
                'to': settings.GMAIL_EMAIL_ADDRESS,
                'subject': 'Re: Hỏi về học bổng XYZ',
                'date': '2024-08-06T14:00:00Z',
                'content': 'Dạ em cảm ơn phòng. Vậy hồ sơ em cần chuẩn bị những gì ạ?',
                'attachments': []
            },
            {
                'from': settings.GMAIL_EMAIL_ADDRESS,
                'to': 'student.e@email.com',
                'subject': 'Re: Hỏi về học bổng XYZ',
                'date': '2024-08-06T16:30:00Z',
                'content': 'Chào em, Hồ sơ em chuẩn bị gồm: 1. Đơn xin học bổng (theo mẫu A), 2. Bảng điểm in từ portal sinh viên. Thân,',
                'attachments': []
            }
        ],
    },
    {
        "test_name": "Case 6: New thread with no question, just a notification",
        "description": "Tests an edge case to ensure the system doesn't hallucinate questions where there are none.",
        "thread_emails": [
            {
                'from': 'student.f@email.com',
                'to': settings.GMAIL_EMAIL_ADDRESS,
                'subject': 'Báo cáo: Đã hoàn thành bổ sung hồ sơ',
                'date': '2024-08-07T10:00:00Z',
                'content': 'Dạ em gửi email này để báo cáo là em đã nộp bổ sung giấy tờ còn thiếu tại văn phòng rồi ạ. Em cảm ơn.',
                'attachments': []
            }
        ],
        "existing_summary": None,
    },
    {
        "test_name": "Case 7: Update thread with old summary format (backward compatibility test)",
        "description": "Ensures the system can gracefully handle old summaries that don't have the separator.",
        "existing_summary": "Sinh viên Trần Văn G hỏi về việc xin miễn giảm học phí cho học kỳ 2, đã nộp đơn và đang chờ kết quả.",
        "thread_emails": [
             {
                'from': 'student.g@email.com',
                'to': settings.GMAIL_EMAIL_ADDRESS,
                'subject': 'Re: Xin miễn giảm học phí',
                'date': '2024-08-08T16:00:00Z',
                'content': 'Dạ em muốn hỏi thêm là khi nào thì có kết quả xét duyệt ạ?',
                'attachments': []
            }
        ],
    },
]


async def run_test():
    """
    Runs the test suite for _extract_questions_with_gemini.
    """
    logging.info("Initializing GmailHandler for testing...")
    # We don't need a real token_path as we are not calling Gmail APIs directly, only Gemini.
    handler = GmailHandler()
    
    if not handler.gemini_processor:
        logging.error("Gemini processor failed to initialize. Aborting test.")
        return

    for i, test_case in enumerate(TEST_CASES):
        logging.info(f"\n{'='*20} Running Test {i+1}: {test_case['test_name']} {'='*20}")
        logging.info(f"Description: {test_case['description']}")
        
        thread_emails = test_case["thread_emails"]
        existing_summary = test_case.get("existing_summary")
        
        logging.info("--- Input ---")
        logging.info(f"Existing Summary: {json.dumps(existing_summary, ensure_ascii=False, indent=2)}")
        logging.info(f"Thread Emails: {json.dumps(thread_emails, ensure_ascii=False, indent=2, default=lambda o: '<bytes_data>')}")
        
        try:
            # Step 1: Create a Gemini conversation
            conversation = await handler._create_gemini_conversation_for_thread(thread_emails)
            if not conversation:
                logging.error("Failed to create Gemini conversation.")
                continue

            # Step 2: Call the target function
            questions, context_summary = await handler._extract_questions_with_gemini(
                conversation,
                thread_emails,
                existing_summary
            )

            logging.info("--- Output ---")
            logging.info(f"Extracted Questions: {json.dumps(questions, ensure_ascii=False, indent=2)}")
            
            # Split and display context summary for clarity
            if KNOWLEDGE_SUMMARY_SEPARATOR in context_summary:
                conv_summary, know_summary = context_summary.split(KNOWLEDGE_SUMMARY_SEPARATOR, 1)
                logging.info(f"Conversation Summary:\n---\n{conv_summary.strip()}\n---")
                logging.info(f"Knowledge Summary:\n---\n{know_summary.strip()}\n---")
            else:
                logging.info(f"Context Summary (single part):\n---\n{context_summary.strip()}\n---")

        except Exception as e:
            logging.error(f"An error occurred during test case '{test_case['test_name']}': {e}", exc_info=True)
        
        # Pause between tests to avoid hitting API rate limits
        await asyncio.sleep(20) # Increased sleep time


if __name__ == "__main__":
    logging.info("Starting Gemini extraction test script.")
    logging.warning("This script will make REAL API calls to Google Gemini which may incur costs.")
    
    asyncio.run(run_test()) 