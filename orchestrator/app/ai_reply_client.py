"""
AI Reply Generator Client

Communicates with the AI Reply Generator service to generate email replies.
"""
import os
import httpx
from typing import Optional
import logging
from app.models import AIReplyResponse

logger = logging.getLogger(__name__)


class AIReplyClient:
    """Client for AI Reply Generator service"""
    
    def __init__(self, base_url: str, timeout: int = 60):
        """
        Initialize AI Reply Generator client.
        
        Args:
            base_url: Base URL of AI Reply Generator service
            timeout: Request timeout in seconds (longer for AI generation)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    async def generate_reply(
        self,
        message_id: str,
        edit_instructions: Optional[str] = None
    ) -> Optional[AIReplyResponse]:
        """
        Generate an AI reply for an email.
        
        Args:
            message_id: Email message ID
            edit_instructions: Optional instructions for editing the reply
            
        Returns:
            AI reply response or None if generation fails
        """
        try:
            payload = {"email_message_id": message_id}
            
            # Add edit instructions if provided
            if edit_instructions:
                payload["context_instructions"] = edit_instructions
                logger.info(f"Generating AI reply for {message_id} with edit instructions: {edit_instructions}")
            else:
                logger.info(f"Generating AI reply for {message_id}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/generate-reply",
                    json=payload
                )
                
                if response.status_code == 404:
                    logger.error(f"Email {message_id} not found in AI Reply Generator")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                ai_response = AIReplyResponse(**data)
                logger.info(f"AI reply generated for {message_id}: {ai_response.reply_length} chars")
                
                return ai_response
                
        except httpx.TimeoutException as e:
            logger.error(f"Timeout generating AI reply for {message_id}: {e}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP error generating AI reply for {message_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error generating AI reply for {message_id}: {e}")
            return None
    
    async def health_check(self) -> bool:
        """
        Check if AI Reply Generator service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"AI Reply Generator health check failed: {e}")
            return False


def get_ai_reply_client() -> AIReplyClient:
    """
    Get AI Reply Generator client instance from environment variables.
    
    Returns:
        AIReplyClient instance
    """
    base_url = os.getenv('AI_REPLY_GENERATOR_URL', 'http://localhost:8002')
    return AIReplyClient(base_url)
