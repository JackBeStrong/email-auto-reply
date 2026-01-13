"""
Pydantic models for the Orchestrator service
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# Workflow State Models
class WorkflowStateCreate(BaseModel):
    """Model for creating a new workflow state"""
    message_id: str
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[str] = None
    email_body_preview: Optional[str] = None
    current_state: str = "pending"
    timeout_at: Optional[datetime] = None


class WorkflowStateUpdate(BaseModel):
    """Model for updating workflow state"""
    current_state: Optional[str] = None
    previous_state: Optional[str] = None
    ai_reply_text: Optional[str] = None
    ai_reply_generated_at: Optional[datetime] = None
    sms_message_id: Optional[str] = None
    sms_sent_at: Optional[datetime] = None
    sms_phone_number: Optional[str] = None
    user_command: Optional[str] = None
    user_edit_instructions: Optional[str] = None
    user_responded_at: Optional[datetime] = None
    edit_iteration: Optional[int] = None
    reply_sent_at: Optional[datetime] = None
    reply_message_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None
    timeout_at: Optional[datetime] = None


class WorkflowStateResponse(BaseModel):
    """Model for workflow state response"""
    id: int
    message_id: str
    email_subject: Optional[str]
    email_from: Optional[str]
    email_to: Optional[str]
    email_body_preview: Optional[str]
    current_state: str
    previous_state: Optional[str]
    ai_reply_text: Optional[str]
    ai_reply_generated_at: Optional[datetime]
    sms_message_id: Optional[str]
    sms_sent_at: Optional[datetime]
    sms_phone_number: Optional[str]
    user_command: Optional[str]
    user_edit_instructions: Optional[str]
    user_responded_at: Optional[datetime]
    edit_iteration: int
    reply_sent_at: Optional[datetime]
    reply_message_id: Optional[str]
    error_message: Optional[str]
    retry_count: int
    created_at: datetime
    updated_at: datetime
    timeout_at: Optional[datetime]

    class Config:
        from_attributes = True


# Email Models (from Email Monitor)
class EmailDetail(BaseModel):
    """Email details from Email Monitor"""
    message_id: str
    subject: Optional[str]
    from_address: str
    to_address: str
    body_text: Optional[str]
    body_html: Optional[str]
    in_reply_to: Optional[str]
    references: Optional[str]
    received_at: datetime
    status: str


# AI Reply Models
class AIReplyRequest(BaseModel):
    """Request to AI Reply Generator"""
    message_id: str
    edit_instructions: Optional[str] = None


class AIReplyResponse(BaseModel):
    """Response from AI Reply Generator"""
    message_id: str
    reply_text: str
    reply_length: int
    generated_at: str


# SMS Models
class SMSRequest(BaseModel):
    """Request to SMS Gateway"""
    phone_number: str
    message: str


class SMSResponse(BaseModel):
    """Response from SMS Gateway"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class IncomingSMSPayload(BaseModel):
    """Payload from incoming SMS webhook"""
    messageId: str
    message: str
    phoneNumber: str
    simNumber: int
    receivedAt: str


class IncomingSMSWebhook(BaseModel):
    """Incoming SMS webhook from SMS Gateway"""
    deviceId: str
    event: str
    id: str
    payload: IncomingSMSPayload
    webhookId: str


# Command Parser Models
class ParsedCommand(BaseModel):
    """Parsed SMS command"""
    command_type: str  # 'approve', 'edit', 'ignore', 'unknown'
    edit_instructions: Optional[str] = None
    raw_message: str


# Health Check Models
class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    workflows: dict
    last_poll: Optional[datetime]
    uptime_seconds: float


# Workflow Statistics
class WorkflowStatistics(BaseModel):
    """Workflow statistics"""
    total_workflows: int
    pending: int
    ai_generating: int
    awaiting_user: int
    completed_today: int
    failed: int
    timeout: int
    average_response_time_minutes: Optional[float]
