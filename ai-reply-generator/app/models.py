"""
Data models for AI Reply Generator service
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DraftStatus(str, Enum):
    """Status of a reply draft"""
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    SENT = "sent"
    IGNORED = "ignored"
    FAILED = "failed"


class UserAction(str, Enum):
    """User action on a draft"""
    APPROVE = "approve"
    EDIT = "edit"
    IGNORE = "ignore"


class ToneType(str, Enum):
    """Tone for reply generation"""
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    TECHNICAL = "technical"
    FRIENDLY = "friendly"


class GenerateReplyRequest(BaseModel):
    """Request to generate a reply for an email"""
    email_message_id: str = Field(..., description="Email message ID from email-monitor")
    tone: ToneType = Field(default=ToneType.PROFESSIONAL, description="Desired tone for the reply")
    max_length: Optional[int] = Field(default=None, description="Maximum length in characters (optional)")
    context_instructions: Optional[str] = Field(default=None, description="Additional context or instructions")


class GenerateReplyResponse(BaseModel):
    """Response after generating a reply"""
    draft_id: str = Field(..., description="Unique short ID for this draft (e.g., 'A7B2')")
    full_draft: str = Field(..., description="Full generated reply text")
    short_summary: Optional[str] = Field(None, description="Short summary for SMS (≤150 chars)")
    length: int = Field(..., description="Length of full draft in characters")
    is_sms_friendly: bool = Field(..., description="True if draft fits in SMS (≤300 chars)")
    tokens_used: int = Field(..., description="Total tokens used (input + output)")
    model_version: str = Field(..., description="Claude model version used")
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class DraftActionRequest(BaseModel):
    """Request to perform an action on a draft"""
    action: UserAction = Field(..., description="Action to perform")
    edited_text: Optional[str] = Field(None, description="Edited reply text (required for 'edit' action)")


class DraftActionResponse(BaseModel):
    """Response after performing an action on a draft"""
    draft_id: str
    status: DraftStatus
    action: UserAction
    final_reply: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReplyDraft(BaseModel):
    """Complete reply draft with all metadata"""
    id: int
    draft_id: str
    email_message_id: str
    full_draft: str
    short_summary: Optional[str] = None
    generated_at: datetime
    tokens_used: int
    model_version: str
    status: DraftStatus
    user_action: Optional[UserAction] = None
    user_action_at: Optional[datetime] = None
    final_reply: Optional[str] = None
    sent_at: Optional[datetime] = None


class DraftPreview(BaseModel):
    """Preview of a draft for display"""
    draft_id: str
    email_subject: str
    email_from: str
    email_received_at: datetime
    full_draft: str
    short_summary: Optional[str] = None
    is_sms_friendly: bool
    status: DraftStatus
    generated_at: datetime


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str = "ai-reply-generator"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    claude_api_available: bool = False
    database_connected: bool = False
