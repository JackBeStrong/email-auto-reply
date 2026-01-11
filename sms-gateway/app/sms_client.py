"""Client for communicating with Android SMS Gateway app."""

import logging
from typing import Optional

import httpx

from .models import MessageStatus

logger = logging.getLogger(__name__)


class SMSGatewayClient:
    """Client for Android SMS Gateway (sms-gate.app)."""

    def __init__(
        self,
        gateway_url: str,
        username: str,
        password: str,
        timeout: float = 30.0,
    ):
        """
        Initialize SMS Gateway client.

        Args:
            gateway_url: Base URL of the Android gateway (e.g., http://192.168.1.224:8080)
            username: Basic auth username
            password: Basic auth password
            timeout: Request timeout in seconds
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.auth = (username, password)
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout, auth=self.auth)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def send_sms(self, to: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Send an SMS via the Android gateway.

        Args:
            to: Destination phone number (E.164 format, e.g., +61430562793)
            message: SMS message content

        Returns:
            Tuple of (success, message_id, error_message)
        """
        client = await self._get_client()

        payload = {
            "phoneNumbers": [to],
            "message": message,
        }

        try:
            response = await client.post(
                f"{self.gateway_url}/message",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            message_id = data.get("id")
            return True, message_id, None

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
            logger.error(f"Failed to send SMS: {error_msg}")
            return False, None, error_msg

        except httpx.RequestError as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(f"Failed to send SMS: {error_msg}")
            return False, None, error_msg

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.exception("Failed to send SMS")
            return False, None, error_msg

    async def check_status(self, message_id: str) -> MessageStatus:
        """
        Check the delivery status of a sent message.

        Args:
            message_id: The message ID returned from send_sms

        Returns:
            MessageStatus enum value
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.gateway_url}/message/{message_id}",
            )
            response.raise_for_status()

            data = response.json()
            state = data.get("state", "").lower()

            status_map = {
                "pending": MessageStatus.PENDING,
                "processed": MessageStatus.SENT,
                "sent": MessageStatus.SENT,
                "delivered": MessageStatus.DELIVERED,
                "failed": MessageStatus.FAILED,
            }
            return status_map.get(state, MessageStatus.PENDING)

        except Exception as e:
            logger.error(f"Failed to check message status: {e}")
            return MessageStatus.PENDING

    async def health_check(self) -> bool:
        """
        Check if the Android gateway is reachable.

        Returns:
            True if gateway is healthy, False otherwise
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.gateway_url}/health",
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False
