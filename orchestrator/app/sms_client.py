"""
SMS Gateway Client

Communicates with the SMS Gateway service to send SMS messages.
"""
import os
import httpx
from typing import Optional
import logging
from app.models import SMSRequest, SMSResponse

logger = logging.getLogger(__name__)


class SMSClient:
    """Client for SMS Gateway service"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        """
        Initialize SMS Gateway client.
        
        Args:
            base_url: Base URL of SMS Gateway service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    async def send_sms(self, phone_number: str, message: str) -> Optional[SMSResponse]:
        """
        Send an SMS message.
        
        Args:
            phone_number: Recipient phone number
            message: SMS message text
            
        Returns:
            SMS response or None if sending fails
        """
        try:
            logger.info(f"Sending SMS to {phone_number}: {message[:50]}...")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/sms/send",
                    json={
                        "to": phone_number,
                        "message": message
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                sms_response = SMSResponse(**data)
                
                if sms_response.success:
                    logger.info(f"SMS sent successfully to {phone_number}, message_id: {sms_response.message_id}")
                else:
                    logger.error(f"SMS sending failed: {sms_response.error}")
                
                return sms_response
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error sending SMS: {e}")
            return SMSResponse(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return SMSResponse(success=False, error=str(e))
    
    async def health_check(self) -> bool:
        """
        Check if SMS Gateway service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"SMS Gateway health check failed: {e}")
            return False


def get_sms_client() -> SMSClient:
    """
    Get SMS Gateway client instance from environment variables.
    
    Returns:
        SMSClient instance
    """
    base_url = os.getenv('SMS_GATEWAY_URL', 'http://localhost:8000')
    return SMSClient(base_url)


def format_sms_notification(
    email_from: str,
    email_subject: str,
    email_body_preview: str,
    ai_reply: str,
    message_id: str,
    orchestrator_base_url: str = 'https://sms.jackan.xyz',
    format_type: str = 'condensed'
) -> str:
    """
    Format an SMS notification with email details and AI reply.
    
    For long drafts, generates a URL to view the full draft instead of truncating.
    
    Args:
        email_from: Sender email address
        email_subject: Email subject
        email_body_preview: Preview of email body
        ai_reply: AI-generated reply text
        message_id: Email message ID (used for draft URL)
        orchestrator_base_url: Base URL for orchestrator service
        format_type: 'condensed' or 'multipart'
        
    Returns:
        Formatted SMS message (with URL if draft is too long)
    """
    # Extract sender name from email address
    sender_name = email_from.split('<')[0].strip() if '<' in email_from else email_from.split('@')[0]
    
    # Truncate sender name if too long
    if len(sender_name) > 20:
        sender_name = sender_name[:20]
    
    # Truncate body preview
    max_body_length = 50
    if len(email_body_preview) > max_body_length:
        body_preview = email_body_preview[:max_body_length] + "..."
    else:
        body_preview = email_body_preview
    
    # Calculate if we need to use URL approach
    # SMS limit: ~160 chars for single SMS, ~320 for 2 segments
    # We'll use URL if draft would exceed 160 chars in total message
    
    footer = "\n\n1=Send 2=Edit 3=Ignore"
    header = f"📧 {sender_name}: \"{body_preview}\"\n\n"
    
    # Try inline draft first
    inline_draft = f"Draft: \"{ai_reply}\""
    inline_message = header + inline_draft + footer
    
    # If message fits in single SMS (160 chars), use inline
    if len(inline_message) <= 160:
        return inline_message
    
    # Otherwise, use URL approach
    # URL encode message_id for safety
    import urllib.parse
    encoded_message_id = urllib.parse.quote(message_id, safe='')
    draft_url = f"{orchestrator_base_url}/drafts/{encoded_message_id}"
    
    url_message = (
        f"📧 {sender_name}: \"{body_preview}\"\n\n"
        f"View draft: {draft_url}\n\n"
        f"1=Send 2=Edit 3=Ignore"
    )
    
    return url_message
