"""Pydantic models for SMS Gateway service."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageDirection(str, Enum):
    """Direction of SMS message."""
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class MessageStatus(str, Enum):
    """Status of SMS message."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RECEIVED = "received"


class SendSMSRequest(BaseModel):
    """Request model for sending an SMS."""
    to: str = Field(..., description="Phone number to send SMS to (E.164 format preferred)")
    message: str = Field(..., min_length=1, max_length=1600, description="SMS message content")


class SendSMSResponse(BaseModel):
    """Response model after sending an SMS."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class WebhookPayload(BaseModel):
    """Nested payload within webhook from Android SMS Gateway app."""
    messageId: str = Field(..., description="Message ID")
    message: str = Field(..., description="SMS message content")
    phoneNumber: str = Field(..., description="Sender phone number")
    simNumber: Optional[int] = Field(default=None, description="SIM card number")
    receivedAt: str = Field(..., description="Timestamp when message was received")


class IncomingSMSWebhook(BaseModel):
    """Webhook payload for incoming SMS from Android gateway.
    
    Based on Android SMS Gateway webhook format:
    https://capcom6.github.io/android-sms-gateway/features/webhooks/
    
    Example:
    {
      "deviceId": "device_abc123",
      "event": "sms:received",
      "id": "webhook_xyz789",
      "payload": {
        "messageId": "msg_12345abcde",
        "message": "Received SMS text",
        "phoneNumber": "+19162255887",
        "simNumber": 1,
        "receivedAt": "2024-06-07T11:41:31.000+07:00"
      },
      "webhookId": "webhook_xyz789"
    }
    """
    deviceId: str = Field(..., description="Device ID from Android app")
    event: str = Field(..., description="Event type (e.g., sms:received)")
    id: str = Field(..., description="Webhook event ID")
    payload: WebhookPayload = Field(..., description="SMS message payload")
    webhookId: str = Field(..., description="Webhook ID")

    model_config = ConfigDict(populate_by_name=True)


class SMSMessage(BaseModel):
    """Stored SMS message record."""
    id: str
    direction: MessageDirection
    phone_number: str
    message: str
    status: MessageStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None


class SMSHistoryResponse(BaseModel):
    """Response model for SMS history endpoint."""
    messages: list[SMSMessage]
    total: int
    page: int = 1
    page_size: int = 50
