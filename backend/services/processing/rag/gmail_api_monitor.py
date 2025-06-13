import logging
import asyncio

logger = logging.getLogger(__name__)

class GmailAPIMonitor:
    """Simple Gmail API monitor using polling."""
    
    def __init__(self, gmail_handler=None, poll_interval: int = 30):
        self.gmail_handler = gmail_handler
        self.running = False
        self.poll_interval = poll_interval
    
    async def start_monitoring(self):
        self.running = True
        logger.info(f"Starting Gmail API polling (interval: {self.poll_interval}s)")
        
        try:
            while self.running:
                if self.gmail_handler and self.gmail_handler.service:
                    results = self.gmail_handler.service.users().messages().list(
                        userId='me',
                        q="is:unread"
                    ).execute()
                    
                    messages = results.get('messages', [])
                    unread_count = len(messages)
                    
                    if unread_count > 0:
                        logger.info(f"Found {unread_count} unread emails")
                        await self.gmail_handler.process_unread_email()
                
                await asyncio.sleep(self.poll_interval)
                    
        except asyncio.CancelledError:
            logger.info("Monitoring cancelled")
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.stop_monitoring()
    
    async def stop_monitoring(self):
        self.running = False
        logger.info("Stopped Gmail API monitoring")

def create_gmail_api_monitor(gmail_handler=None, poll_interval: int = 30) -> GmailAPIMonitor:
    return GmailAPIMonitor(gmail_handler=gmail_handler, poll_interval=poll_interval) 