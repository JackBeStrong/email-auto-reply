"""FastAPI SMS Gateway service."""

import hashlib
import hmac
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global sms_client

    gateway_url = os.getenv("ANDROID_GATEWAY_URL", "http://localhost:8080")
    sms_client = SMSGatewayClient(gateway_url)
    logger.info(f"SMS Gateway client initialized with URL: {gateway_url}")

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


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature for security."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    gateway_healthy = False
    if sms_client:
        gateway_healthy = await sms_client.health_check()

    return {
        "status": "healthy",
        "gateway_connected": gateway_healthy,
        "timestamp": datetime.utcnow().isoformat(),
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
            timestamp=datetime.utcnow(),
        )
        message_store.append(stored_message)
        logger.info(f"SMS sent successfully, message_id: {msg_id}")

        return SendSMSResponse(success=True, message_id=msg_id)
    else:
        logger.error(f"Failed to send SMS: {error}")
        return SendSMSResponse(success=False, error=error)


@app.post("/sms/incoming")
async def incoming_sms_webhook(
    webhook: IncomingSMSWebhook,
    x_webhook_signature: Optional[str] = Header(None),
):
    """
    Webhook endpoint to receive incoming SMS from Android gateway.

    The Android SMS gateway app should be configured to POST to this endpoint
    when a new SMS is received on the phone.
    """
    webhook_secret = os.getenv("WEBHOOK_SECRET")

    # Verify signature if secret is configured (optional but recommended)
    # Note: Signature verification depends on gateway app capabilities
    if webhook_secret and x_webhook_signature:
        # This is a simplified check - actual implementation depends on gateway
        logger.debug("Webhook signature verification enabled")

    logger.info(f"Received SMS from {webhook.from_number}: {webhook.message[:50]}...")

    # Store the incoming message
    stored_message = SMSMessage(
        id=str(uuid.uuid4()),
        direction=MessageDirection.INCOMING,
        phone_number=webhook.from_number,
        message=webhook.message,
        status=MessageStatus.RECEIVED,
        timestamp=webhook.timestamp or datetime.utcnow(),
        metadata={"device_id": webhook.device_id} if webhook.device_id else None,
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
