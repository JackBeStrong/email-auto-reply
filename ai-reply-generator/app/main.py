"""
AI Reply Generator FastAPI application
"""
import os
import logging
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
import httpx

# Load environment variables from .env file
load_dotenv()

from app.models import (
    GenerateReplyRequest,
    GenerateReplyResponse,
    DraftActionRequest,
    DraftActionResponse,
    ReplyDraft,
    DraftPreview,
    HealthResponse,
    DraftStatus,
    UserAction,
    ToneType
)
from app.database import DatabaseManager
from app.claude_client import ClaudeClient
from app.reply_formatter import ReplyFormatter

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DB_HOST = os.getenv("DB_HOST", "192.168.1.228")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "email_auto_reply")
DB_USER = os.getenv("DB_USER", "readwrite")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Build database URL
DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

EMAIL_MONITOR_URL = os.getenv("EMAIL_MONITOR_URL", "http://localhost:8001")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8002"))
SMS_FRIENDLY_MAX_LENGTH = int(os.getenv("SMS_FRIENDLY_MAX_LENGTH", "300"))

# Global instances
db_manager: Optional[DatabaseManager] = None
claude_client: Optional[ClaudeClient] = None
reply_formatter = ReplyFormatter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global db_manager, claude_client
    
    # Startup
    logger.info("Starting AI Reply Generator service...")
    
    # Initialize database
    db_manager = DatabaseManager(DATABASE_URL)
    db_manager.init_tables()
    logger.info("Database initialized")
    
    # Initialize Claude client
    try:
        claude_client = ClaudeClient()
        logger.info("Claude API client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Claude client: {e}")
        raise
    
    logger.info(f"AI Reply Generator service started on port {SERVICE_PORT}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI Reply Generator service...")
    if db_manager:
        db_manager.close()
    logger.info("Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="AI Reply Generator",
    description="Generates AI-powered email reply drafts using Claude API",
    version="0.1.0",
    lifespan=lifespan
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    claude_available = False
    db_connected = False
    
    try:
        if claude_client:
            claude_available = claude_client.check_health()
    except Exception as e:
        logger.error(f"Claude health check failed: {e}")
    
    try:
        if db_manager:
            db_connected = db_manager.check_connection()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    return HealthResponse(
        status="healthy" if (claude_available and db_connected) else "degraded",
        claude_api_available=claude_available,
        database_connected=db_connected
    )


@app.post("/generate-reply", response_model=GenerateReplyResponse)
async def generate_reply(request: GenerateReplyRequest):
    """
    Generate a reply draft for an email
    
    This endpoint:
    1. Fetches email context from email-monitor service
    2. Generates reply using Claude API
    3. Creates summary if reply is too long for SMS
    4. Stores draft in database
    5. Returns draft details
    """
    try:
        # Fetch email context from email-monitor service
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{EMAIL_MONITOR_URL}/emails/{request.email_message_id}"
            )
            
            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Email {request.email_message_id} not found"
                )
            
            response.raise_for_status()
            email_data = response.json()
        
        logger.info(f"Generating reply for email {request.email_message_id}")
        
        # Extract email details
        email_subject = email_data.get("subject", "")
        email_from = email_data.get("from_address", "")
        email_body = email_data.get("body_text") or email_data.get("body_html", "")
        thread_context = None  # TODO: Fetch thread context if available
        
        # Generate reply using Claude
        full_draft, tokens_used = await claude_client.generate_reply(
            email_subject=email_subject,
            email_from=email_from,
            email_body=email_body,
            tone=request.tone,
            thread_context=thread_context,
            context_instructions=request.context_instructions,
            max_length=request.max_length
        )
        
        # Clean the reply
        full_draft = reply_formatter.clean_reply_text(full_draft)
        
        # Validate reply
        is_valid, error_msg = reply_formatter.validate_reply(full_draft)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Generated reply validation failed: {error_msg}"
            )
        
        # Check if SMS-friendly
        is_sms_friendly = reply_formatter.is_sms_friendly(full_draft)
        
        # Generate summary if needed
        short_summary = None
        if not is_sms_friendly:
            try:
                short_summary, summary_tokens = await claude_client.generate_summary(full_draft)
                tokens_used += summary_tokens
            except Exception as e:
                logger.warning(f"Failed to generate summary: {e}")
                # Fallback to truncation
                short_summary = full_draft[:147] + "..."
        
        # Store draft in database
        draft_id = db_manager.create_draft(
            email_message_id=request.email_message_id,
            full_draft=full_draft,
            short_summary=short_summary,
            tokens_used=tokens_used,
            model_version=claude_client.DEFAULT_MODEL
        )
        
        logger.info(f"Created draft {draft_id} for email {request.email_message_id}")
        
        return GenerateReplyResponse(
            draft_id=draft_id,
            full_draft=full_draft,
            short_summary=short_summary,
            length=len(full_draft),
            is_sms_friendly=is_sms_friendly,
            tokens_used=tokens_used,
            model_version=claude_client.DEFAULT_MODEL
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating reply: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reply: {str(e)}"
        )


@app.get("/drafts/{draft_id}", response_model=ReplyDraft)
async def get_draft(draft_id: str):
    """Get a draft by ID"""
    draft = db_manager.get_draft(draft_id)
    
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found"
        )
    
    return ReplyDraft(**draft)


@app.put("/drafts/{draft_id}/action", response_model=DraftActionResponse)
async def update_draft_action(draft_id: str, request: DraftActionRequest):
    """
    Perform an action on a draft (approve/edit/ignore)
    
    For 'edit' action with edit_instruction, this will regenerate the draft
    """
    # Check if draft exists
    draft = db_manager.get_draft(draft_id)
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found"
        )
    
    try:
        final_reply = None
        
        if request.action == UserAction.EDIT and request.edited_text:
            # User provided edited text directly
            final_reply = request.edited_text
            
            # Validate edited text
            is_valid, error_msg = reply_formatter.validate_reply(final_reply)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Edited text validation failed: {error_msg}"
                )
        
        # Update draft in database
        success = db_manager.update_draft_action(
            draft_id=draft_id,
            action=request.action.value,
            final_reply=final_reply
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update draft"
            )
        
        # Determine status
        if request.action == UserAction.APPROVE:
            new_status = DraftStatus.APPROVED
        elif request.action == UserAction.EDIT:
            new_status = DraftStatus.EDITED
        else:
            new_status = DraftStatus.IGNORED
        
        logger.info(f"Updated draft {draft_id} with action: {request.action.value}")
        
        return DraftActionResponse(
            draft_id=draft_id,
            status=new_status,
            action=request.action,
            final_reply=final_reply
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating draft action: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update draft: {str(e)}"
        )


@app.get("/drafts/{draft_id}/preview", response_model=DraftPreview)
async def get_draft_preview(draft_id: str):
    """Get a preview of a draft with email context"""
    draft = db_manager.get_draft(draft_id)
    
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found"
        )
    
    try:
        # Fetch email context
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{EMAIL_MONITOR_URL}/emails/{draft['email_message_id']}"
            )
            response.raise_for_status()
            email_data = response.json()
        
        return DraftPreview(
            draft_id=draft['draft_id'],
            email_subject=email_data.get('subject', ''),
            email_from=email_data.get('from_address', ''),
            email_received_at=email_data.get('received_at'),
            full_draft=draft['full_draft'],
            short_summary=draft['short_summary'],
            is_sms_friendly=len(draft['full_draft']) <= SMS_FRIENDLY_MAX_LENGTH,
            status=DraftStatus(draft['status']),
            generated_at=draft['generated_at']
        )
        
    except Exception as e:
        logger.error(f"Error fetching draft preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch draft preview: {str(e)}"
        )


@app.get("/drafts")
async def list_drafts(status: Optional[str] = None, limit: int = 100):
    """List all drafts, optionally filtered by status"""
    try:
        if status == "pending":
            drafts = db_manager.get_pending_drafts(limit=limit)
        else:
            drafts = db_manager.get_all_drafts(limit=limit)
        
        return {
            "drafts": drafts,
            "count": len(drafts)
        }
        
    except Exception as e:
        logger.error(f"Error listing drafts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list drafts: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
