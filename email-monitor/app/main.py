"""
Email Monitor Service - Phase 2
FastAPI application that monitors Gmail inbox via IMAP
"""
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .imap_client import IMAPClient
from .models import EmailMessage, EmailFilter, ProcessedEmail
from .database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "120"))  # seconds

# Database configuration
DB_HOST = os.getenv("DB_HOST", "192.168.1.228")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "email_auto_reply")
DB_USER = os.getenv("DB_USER", "readwrite")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Build database URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Global state
db_manager: DatabaseManager = None
email_filter: EmailFilter = None
polling_task: asyncio.Task = None


async def poll_emails():
    """Background task that polls for new emails"""
    logger.info(f"Starting email polling loop (interval: {POLL_INTERVAL}s)")
    
    while True:
        try:
            logger.debug("Polling for new emails...")
            
            # Connect to IMAP server
            with IMAPClient(IMAP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD, IMAP_PORT) as client:
                # Fetch unread emails
                emails = client.fetch_unread_emails(limit=20)
                
                new_emails = []
                for email_msg in emails:
                    # Skip if already processed
                    if db_manager.is_processed(email_msg.message_id):
                        logger.debug(f"Skipping already processed email: {email_msg.message_id}")
                        continue
                    
                    # Apply filtering
                    if not email_filter.should_process(email_msg):
                        logger.info(f"Filtered out email from {email_msg.from_address}: {email_msg.subject}")
                        db_manager.mark_processed(
                            message_id=email_msg.message_id,
                            subject=email_msg.subject,
                            from_address=email_msg.from_address,
                            to_addresses=email_msg.to_addresses,
                            received_at=email_msg.received_at,
                            status="filtered",
                            error_message="Filtered by whitelist/blacklist rules",
                            thread_id=email_msg.thread_id,
                            in_reply_to=email_msg.in_reply_to
                        )
                        continue
                    
                    # Mark as processed with pending status
                    db_manager.mark_processed(
                        message_id=email_msg.message_id,
                        subject=email_msg.subject,
                        from_address=email_msg.from_address,
                        to_addresses=email_msg.to_addresses,
                        received_at=email_msg.received_at,
                        status="pending",
                        thread_id=email_msg.thread_id,
                        in_reply_to=email_msg.in_reply_to
                    )
                    new_emails.append(email_msg)
                    logger.info(f"New email from {email_msg.from_address}: {email_msg.subject}")
                
                if new_emails:
                    logger.info(f"Found {len(new_emails)} new emails to process")
                    # TODO: Send to AI Reply Generator (Phase 3)
                    # For now, just log them
                    for email_msg in new_emails:
                        logger.info(f"  - {email_msg.from_address}: {email_msg.subject}")
                else:
                    logger.debug("No new emails to process")
        
        except Exception as e:
            logger.error(f"Error during email polling: {e}", exc_info=True)
        
        # Wait before next poll
        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global db_manager, email_filter, polling_task
    
    # Startup
    logger.info("Starting Email Monitor Service")
    
    # Validate configuration
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        logger.error("EMAIL_ADDRESS and EMAIL_PASSWORD must be set")
        raise RuntimeError("Missing required email configuration")
    
    if not DB_PASSWORD:
        logger.error("DB_PASSWORD must be set")
        raise RuntimeError("Missing required database configuration")
    
    # Initialize database manager
    db_manager = DatabaseManager(DATABASE_URL)
    logger.info("Database manager initialized")
    
    # Load email filter rules from database
    email_filter = db_manager.get_filter_rules()
    logger.info(f"Email filter configured:")
    logger.info(f"  Whitelist senders: {email_filter.whitelist_senders}")
    logger.info(f"  Blacklist senders: {email_filter.blacklist_senders}")
    logger.info(f"  Whitelist subjects: {email_filter.whitelist_subjects}")
    logger.info(f"  Blacklist subjects: {email_filter.blacklist_subjects}")
    
    # Start polling task
    polling_task = asyncio.create_task(poll_emails())
    
    yield
    
    # Shutdown
    logger.info("Shutting down Email Monitor Service")
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    
    if db_manager:
        db_manager.close()


# Create FastAPI app
app = FastAPI(
    title="Email Monitor Service",
    description="Phase 2: Monitors Gmail inbox via IMAP and filters emails",
    version="1.0.0",
    lifespan=lifespan
)


# API Models
class HealthResponse(BaseModel):
    status: str
    service: str
    processed_emails: int
    pending_emails: int


class EmailListResponse(BaseModel):
    emails: List[Dict[str, Any]]
    total: int


class FilterConfigResponse(BaseModel):
    whitelist_senders: List[str]
    blacklist_senders: List[str]
    whitelist_subjects: List[str]
    blacklist_subjects: List[str]


class FilterRuleRequest(BaseModel):
    rule_type: str  # 'whitelist_sender', 'blacklist_sender', 'whitelist_subject', 'blacklist_subject'
    pattern: str
    description: str = None


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    processed_count = len(db_manager.get_processed_message_ids())
    pending_count = len(db_manager.get_pending_emails())
    
    return HealthResponse(
        status="healthy",
        service="email-monitor",
        processed_emails=processed_count,
        pending_emails=pending_count
    )


@app.get("/emails/pending", response_model=EmailListResponse)
async def get_pending_emails():
    """Get all emails with pending status"""
    pending = db_manager.get_pending_emails()
    
    emails_list = [
        {
            "message_id": msg_id,
            "processed_at": email.processed_at.isoformat(),
            "status": email.status,
            "reply_draft": email.reply_draft
        }
        for msg_id, email in pending.items()
    ]
    
    return EmailListResponse(
        emails=emails_list,
        total=len(emails_list)
    )


@app.get("/emails/processed", response_model=EmailListResponse)
async def get_processed_emails(limit: int = 100):
    """Get all processed emails"""
    all_processed = db_manager.get_all_processed_emails(limit=limit)
    
    emails_list = [
        {
            "message_id": msg_id,
            "processed_at": email.processed_at.isoformat(),
            "status": email.status,
            "reply_draft": email.reply_draft,
            "error_message": email.error_message
        }
        for msg_id, email in all_processed.items()
    ]
    
    return EmailListResponse(
        emails=emails_list,
        total=len(emails_list)
    )


@app.get("/emails/{message_id}")
async def get_email_status(message_id: str):
    """Get status of a specific email"""
    email = db_manager.get_processed_email(message_id)
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    return {
        "message_id": message_id,
        "processed_at": email.processed_at.isoformat(),
        "status": email.status,
        "reply_draft": email.reply_draft,
        "error_message": email.error_message
    }


@app.post("/emails/{message_id}/status")
async def update_email_status(
    message_id: str,
    status: str,
    reply_draft: str = None,
    error_message: str = None
):
    """Update the status of an email"""
    success = db_manager.update_status(
        message_id,
        status,
        reply_draft=reply_draft,
        error_message=error_message
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Email not found")
    
    return {"message": "Status updated successfully"}


@app.get("/filter/config", response_model=FilterConfigResponse)
async def get_filter_config():
    """Get current email filter configuration"""
    # Reload from database to get latest
    current_filter = db_manager.get_filter_rules()
    return FilterConfigResponse(
        whitelist_senders=current_filter.whitelist_senders,
        blacklist_senders=current_filter.blacklist_senders,
        whitelist_subjects=current_filter.whitelist_subjects,
        blacklist_subjects=current_filter.blacklist_subjects
    )


@app.get("/filter/rules")
async def get_filter_rules(include_inactive: bool = False):
    """Get all filter rules"""
    rules = db_manager.get_all_filter_rules(include_inactive=include_inactive)
    return {"rules": rules, "total": len(rules)}


@app.post("/filter/rules")
async def add_filter_rule(rule: FilterRuleRequest):
    """Add a new filter rule"""
    rule_id = db_manager.add_filter_rule(
        rule_type=rule.rule_type,
        pattern=rule.pattern,
        description=rule.description
    )
    
    # Reload filter rules
    global email_filter
    email_filter = db_manager.get_filter_rules()
    
    return {"message": "Filter rule added successfully", "rule_id": rule_id}


@app.delete("/filter/rules/{rule_id}")
async def remove_filter_rule(rule_id: int):
    """Remove a filter rule"""
    success = db_manager.remove_filter_rule(rule_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Filter rule not found")
    
    # Reload filter rules
    global email_filter
    email_filter = db_manager.get_filter_rules()
    
    return {"message": "Filter rule removed successfully"}


@app.post("/cleanup")
async def cleanup_old_entries(days: int = 30):
    """Clean up processed emails older than specified days"""
    removed = db_manager.cleanup_old_entries(days)
    return {"message": f"Cleaned up {removed} old entries"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
