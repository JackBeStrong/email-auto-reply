"""FastAPI SMS Gateway service."""

import hashlib
import hmac
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    android_gateway_url: str = "http://localhost:8080"
    sms_gateway_username: str = ""
    sms_gateway_password: str = ""
    your_phone_number: str = ""
    sms_gateway_webhook_signing_key: str = ""  # Optional: HMAC signing key from Android app

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

from .models import (
    IncomingSMSWebhook,
    MessageDirection,
    MessageStatus,
    SendSMSRequest,
    SendSMSResponse,
    SMSHistoryResponse,
    SMSMessage,
)
from .sms_client import SMSGatewayClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# In-memory message store (replace with database in production)
message_store: list[SMSMessage] = []

# SMS Gateway client instance
sms_client: Optional[SMSGatewayClient] = None


def verify_webhook_signature(payload: str, timestamp: str, signature: str, secret_key: str) -> bool:
    """
    Verify HMAC-SHA256 signature from Android SMS Gateway webhook.
    
    Args:
        payload: Raw request body as string
        timestamp: Unix timestamp from X-Timestamp header
        signature: HMAC signature from X-Signature header
        secret_key: Signing key configured in Android app
    
    Returns:
        True if signature is valid, False otherwise
    """
    if not secret_key:
        logger.warning("No signing key configured, skipping signature verification")
        return True  # Allow webhook if no key is configured
    
    try:
        # Concatenate payload and timestamp
        message = (payload + timestamp).encode()
        
        # Compute expected signature
        expected_signature = hmac.new(
            secret_key.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        
        # Use constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(expected_signature, signature)
        
        if not is_valid:
            logger.warning(f"Invalid webhook signature. Expected: {expected_signature[:10]}..., Got: {signature[:10]}...")
        
        return is_valid
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False


def verify_webhook_timestamp(timestamp: str, max_age_seconds: int = 300) -> bool:
    """
    Verify webhook timestamp to prevent replay attacks.
    
    Args:
        timestamp: Unix timestamp from X-Timestamp header
        max_age_seconds: Maximum age of webhook in seconds (default: 5 minutes)
    
    Returns:
        True if timestamp is within acceptable range, False otherwise
    """
    try:
        webhook_time = int(timestamp)
        current_time = int(time.time())
        age = abs(current_time - webhook_time)
        
        if age > max_age_seconds:
            logger.warning(f"Webhook timestamp too old: {age} seconds")
            return False
        
        return True
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid timestamp format: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global sms_client

    if not settings.sms_gateway_username or not settings.sms_gateway_password:
        logger.warning("SMS_GATEWAY_USERNAME or SMS_GATEWAY_PASSWORD not set")
    
    if not settings.sms_gateway_webhook_signing_key:
        logger.warning("SMS_GATEWAY_WEBHOOK_SIGNING_KEY not set - webhook signature verification disabled")
    else:
        logger.info("Webhook signature verification enabled")

    sms_client = SMSGatewayClient(
        settings.android_gateway_url,
        settings.sms_gateway_username,
        settings.sms_gateway_password,
    )
    logger.info(f"SMS Gateway client initialized with URL: {settings.android_gateway_url}")

    yield

    if sms_client:
        await sms_client.close()
        logger.info("SMS Gateway client closed")


app = FastAPI(
    title="SMS Gateway Service",
    description="2-way SMS gateway service using Android phone",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    gateway_healthy = False
    if sms_client:
        gateway_healthy = await sms_client.health_check()

    return {
        "status": "healthy",
        "gateway_connected": gateway_healthy,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/sms/send", response_model=SendSMSResponse)
async def send_sms(request: SendSMSRequest):
    """
    Send an SMS message via the Android gateway.

    - **to**: Destination phone number (E.164 format preferred, e.g., +14155551234)
    - **message**: SMS content (max 1600 characters for concatenated SMS)
    """
    if not sms_client:
        raise HTTPException(status_code=503, detail="SMS client not initialized")

    logger.info(f"Sending SMS to {request.to}: {request.message[:50]}...")

    success, message_id, error = await sms_client.send_sms(request.to, request.message)

    if success:
        # Store the outgoing message
        msg_id = message_id or str(uuid.uuid4())
        stored_message = SMSMessage(
            id=msg_id,
            direction=MessageDirection.OUTGOING,
            phone_number=request.to,
            message=request.message,
            status=MessageStatus.SENT,
            timestamp=datetime.now(timezone.utc),
        )
        message_store.append(stored_message)
        logger.info(f"SMS sent successfully, message_id: {msg_id}")

        return SendSMSResponse(success=True, message_id=msg_id)
    else:
        logger.error(f"Failed to send SMS: {error}")
        return SendSMSResponse(success=False, error=error)


@app.post("/sms/incoming")
async def incoming_sms_webhook(
    request: Request,
    webhook: IncomingSMSWebhook,
    x_signature: Optional[str] = Header(None),
    x_timestamp: Optional[str] = Header(None),
):
    """
    Webhook endpoint to receive incoming SMS from Android gateway.

    The Android SMS gateway app should be configured to POST to this endpoint
    when a new SMS is received on the phone.
    
    Security:
    - Verifies HMAC-SHA256 signature if WEBHOOK_SIGNING_KEY is configured
    - Validates timestamp to prevent replay attacks (±5 minutes)
    """
    # Verify webhook signature if signing key is configured
    if settings.webhook_signing_key:
        if not x_signature or not x_timestamp:
            logger.warning("Webhook missing signature headers")
            raise HTTPException(
                status_code=401,
                detail="Missing X-Signature or X-Timestamp header"
            )
        
        # Verify timestamp first (prevent replay attacks)
        if not verify_webhook_timestamp(x_timestamp):
            raise HTTPException(
                status_code=401,
                detail="Webhook timestamp invalid or too old"
            )
        
        # Get raw request body for signature verification
        body = await request.body()
        payload = body.decode('utf-8')
        
        # Verify signature
        if not verify_webhook_signature(payload, x_timestamp, x_signature, settings.webhook_signing_key):
            raise HTTPException(
                status_code=401,
                detail="Invalid webhook signature"
            )
        
        logger.info("Webhook signature verified successfully")
    
    logger.info(f"Received SMS from {webhook.payload.phoneNumber}: {webhook.payload.message[:50]}...")

    # Store the incoming message
    stored_message = SMSMessage(
        id=webhook.payload.messageId,
        direction=MessageDirection.INCOMING,
        phone_number=webhook.payload.phoneNumber,
        message=webhook.payload.message,
        status=MessageStatus.RECEIVED,
        timestamp=datetime.now(timezone.utc),  # Parse receivedAt if needed
        metadata={
            "sim_number": webhook.payload.simNumber,
            "received_at": webhook.payload.receivedAt,
            "event": webhook.event
        },
    )
    message_store.append(stored_message)

    # TODO: In Phase 4, this is where we'll trigger the orchestrator
    # to process the user's response (1/2/3 for approve/edit/ignore)

    return {"status": "received", "message_id": stored_message.id}


@app.get("/sms/history", response_model=SMSHistoryResponse)
async def get_sms_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    direction: Optional[MessageDirection] = Query(None, description="Filter by direction"),
    phone_number: Optional[str] = Query(None, description="Filter by phone number"),
):
    """
    Retrieve SMS message history with optional filtering.

    - **page**: Page number (starts at 1)
    - **page_size**: Number of messages per page (max 100)
    - **direction**: Filter by incoming/outgoing
    - **phone_number**: Filter by phone number
    """
    filtered = message_store

    if direction:
        filtered = [m for m in filtered if m.direction == direction]

    if phone_number:
        filtered = [m for m in filtered if m.phone_number == phone_number]

    # Sort by timestamp descending (newest first)
    filtered = sorted(filtered, key=lambda m: m.timestamp, reverse=True)

    # Paginate
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = filtered[start:end]

    return SMSHistoryResponse(
        messages=paginated,
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/sms/{message_id}")
async def get_message(message_id: str):
    """Get a specific SMS message by ID."""
    for msg in message_store:
        if msg.id == message_id:
            return msg

    raise HTTPException(status_code=404, detail="Message not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
