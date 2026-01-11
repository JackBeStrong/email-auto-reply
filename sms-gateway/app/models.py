"""Pydantic models for SMS Gateway service."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class IncomingSMSWebhook(BaseModel):
    """Webhook payload for incoming SMS from Android gateway."""
    from_number: str = Field(..., alias="from", description="Sender phone number")
    message: str = Field(..., description="SMS message content")
    timestamp: Optional[datetime] = Field(default=None, description="Message timestamp")
    device_id: Optional[str] = Field(default=None, description="Android device identifier")

    class Config:
        populate_by_name = True


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
