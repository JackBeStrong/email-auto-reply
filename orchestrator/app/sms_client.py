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
                        "phone_number": phone_number,
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
    format_type: str = 'condensed'
) -> str:
    """
    Format an SMS notification with email details and AI reply.
    
    Args:
        email_from: Sender email address
        email_subject: Email subject
        email_body_preview: Preview of email body
        ai_reply: AI-generated reply text
        format_type: 'condensed' or 'multipart'
        
    Returns:
        Formatted SMS message
    """
    # Extract sender name from email address
    sender_name = email_from.split('<')[0].strip() if '<' in email_from else email_from.split('@')[0]
    
    # Truncate body preview to fit in SMS
    max_body_length = 80
    if len(email_body_preview) > max_body_length:
        body_preview = email_body_preview[:max_body_length] + "..."
    else:
        body_preview = email_body_preview
    
    # Truncate AI reply if too long
    max_reply_length = 150
    if len(ai_reply) > max_reply_length:
        reply_preview = ai_reply[:max_reply_length] + "..."
    else:
        reply_preview = ai_reply
    
    if format_type == 'condensed':
        # Condensed format for single SMS
        message = (
            f"📧 {sender_name}: \"{body_preview}\"\n"
            f"Draft: \"{reply_preview}\"\n"
            f"1=Send 2=Edit 3=Ignore"
        )
    else:
        # Multi-part format (for future implementation)
        message = (
            f"📧 From: {sender_name}\n"
            f"Subject: {email_subject}\n"
            f"Body: \"{body_preview}\"\n"
            f"Draft: \"{reply_preview}\"\n"
            f"Reply: 1=Send 2=Edit 3=Ignore"
        )
    
    return message
