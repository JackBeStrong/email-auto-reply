"""
Email Monitor Client

Communicates with the Email Monitor service to fetch pending emails.
"""
import os
import httpx
from typing import List, Optional
import logging
from app.models import EmailDetail

logger = logging.getLogger(__name__)


class EmailMonitorClient:
    """Client for Email Monitor service"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        """
        Initialize Email Monitor client.
        
        Args:
            base_url: Base URL of Email Monitor service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    async def get_pending_emails(self) -> List[EmailDetail]:
        """
        Get list of pending emails from Email Monitor.
        
        Returns:
            List of pending emails
            
        Raises:
            Exception: If request fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/emails/pending")
                response.raise_for_status()
                
                data = response.json()
                emails = [EmailDetail(**email) for email in data.get('emails', [])]
                
                logger.info(f"Fetched {len(emails)} pending emails from Email Monitor")
                return emails
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching pending emails: {e}")
            raise Exception(f"Failed to fetch pending emails: {e}")
        except Exception as e:
            logger.error(f"Error fetching pending emails: {e}")
            raise Exception(f"Failed to fetch pending emails: {e}")
    
    async def get_email_details(self, message_id: str) -> Optional[EmailDetail]:
        """
        Get details for a specific email.
        
        Args:
            message_id: Email message ID
            
        Returns:
            Email details or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/emails/{message_id}")
                
                if response.status_code == 404:
                    logger.warning(f"Email {message_id} not found")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                return EmailDetail(**data)
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching email {message_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching email {message_id}: {e}")
            return None
    
    async def update_email_status(self, message_id: str, status: str) -> bool:
        """
        Update email status in Email Monitor.
        
        Args:
            message_id: Email message ID
            status: New status (e.g., 'orchestrating', 'sent', 'ignored')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/emails/{message_id}/status",
                    json={"status": status}
                )
                response.raise_for_status()
                
                logger.info(f"Updated email {message_id} status to {status}")
                return True
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error updating email status: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating email status: {e}")
            return False
    
    async def health_check(self) -> bool:
        """
        Check if Email Monitor service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Email Monitor health check failed: {e}")
            return False


def get_email_monitor_client() -> EmailMonitorClient:
    """
    Get Email Monitor client instance from environment variables.
    
    Returns:
        EmailMonitorClient instance
    """
    base_url = os.getenv('EMAIL_MONITOR_URL', 'http://localhost:8001')
    return EmailMonitorClient(base_url)
