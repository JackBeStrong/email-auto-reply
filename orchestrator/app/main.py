"""
Orchestrator Service - Main FastAPI Application

Coordinates the email auto-reply workflow by integrating:
- Email Monitor (fetch pending emails)
- AI Reply Generator (generate replies)
- SMS Gateway (send notifications and receive responses)
- Gmail SMTP (send approved replies)
"""
import os
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from app.models import (
    IncomingSMSWebhook,
    WorkflowStateResponse,
    HealthCheckResponse,
    WorkflowStatistics
)
from app.workflow_manager import get_workflow_manager
from app.database import get_database_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
workflow_manager = None
db_manager = None
background_tasks_running = False
start_time = datetime.utcnow()


async def poll_pending_emails():
    """Background task to poll for pending emails"""
    global workflow_manager, background_tasks_running
    
    poll_interval = int(os.getenv('POLL_INTERVAL', '120'))
    
    logger.info(f"Starting email polling task (interval: {poll_interval}s)")
    
    while background_tasks_running:
        try:
            await workflow_manager.process_pending_emails()
        except Exception as e:
            logger.error(f"Error in email polling task: {e}")
        
        await asyncio.sleep(poll_interval)
    
    logger.info("Email polling task stopped")


async def check_workflow_timeouts():
    """Background task to check for workflow timeouts"""
    global workflow_manager, background_tasks_running
    
    check_interval = 300  # 5 minutes
    
    logger.info(f"Starting timeout check task (interval: {check_interval}s)")
    
    while background_tasks_running:
        try:
            await workflow_manager.check_timeouts()
        except Exception as e:
            logger.error(f"Error in timeout check task: {e}")
        
        await asyncio.sleep(check_interval)
    
    logger.info("Timeout check task stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global workflow_manager, db_manager, background_tasks_running
    
    # Startup
    logger.info("Starting Orchestrator service...")
    
    try:
        # Initialize managers
        workflow_manager = get_workflow_manager()
        db_manager = get_database_manager()
        
        # Start background tasks
        background_tasks_running = True
        asyncio.create_task(poll_pending_emails())
        asyncio.create_task(check_workflow_timeouts())
        
        logger.info("Orchestrator service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start Orchestrator service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Orchestrator service...")
    background_tasks_running = False
    await asyncio.sleep(1)  # Give tasks time to finish
    logger.info("Orchestrator service stopped")


# Create FastAPI app
app = FastAPI(
    title="Email Auto-Reply Orchestrator",
    description="Orchestrates the email auto-reply workflow",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint
    
    Returns service status and workflow statistics
    """
    try:
        stats = db_manager.get_workflow_statistics()
        uptime = (datetime.utcnow() - start_time).total_seconds()
        
        return HealthCheckResponse(
            status="healthy",
            service="orchestrator",
            workflows=stats,
            last_poll=None,  # Could track this if needed
            uptime_seconds=uptime
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/status", response_model=WorkflowStatistics)
async def get_workflow_status():
    """
    Get overall workflow statistics
    
    Returns counts of workflows in different states
    """
    try:
        stats = db_manager.get_workflow_statistics()
        
        return WorkflowStatistics(
            total_workflows=stats['total_workflows'],
            pending=stats['pending'],
            ai_generating=stats['ai_generating'],
            awaiting_user=stats['awaiting_user'],
            completed_today=stats['completed_today'],
            failed=stats['failed'],
            timeout=stats['timeout'],
            average_response_time_minutes=None  # Could calculate if needed
        )
    except Exception as e:
        logger.error(f"Error getting workflow status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/{message_id}", response_model=WorkflowStateResponse)
async def get_workflow(message_id: str):
    """
    Get workflow state for a specific email
    
    Args:
        message_id: Email message ID
        
    Returns:
        Workflow state details
    """
    try:
        workflow = db_manager.get_workflow(message_id)
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return WorkflowStateResponse.model_validate(workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/pending")
async def get_pending_workflows():
    """
    Get list of workflows awaiting user response
    
    Returns:
        List of workflows in 'awaiting_user' state
    """
    try:
        workflows = db_manager.get_workflows_by_state("awaiting_user", limit=50)
        
        return {
            "workflows": [WorkflowStateResponse.model_validate(w) for w in workflows],
            "total": len(workflows)
        }
    except Exception as e:
        logger.error(f"Error getting pending workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/failed")
async def get_failed_workflows():
    """
    Get list of failed workflows
    
    Returns:
        List of workflows in 'failed' state
    """
    try:
        workflows = db_manager.get_workflows_by_state("failed", limit=50)
        
        return {
            "workflows": [WorkflowStateResponse.model_validate(w) for w in workflows],
            "total": len(workflows)
        }
    except Exception as e:
        logger.error(f"Error getting failed workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow/{message_id}/retry")
async def retry_workflow(message_id: str):
    """
    Retry a failed workflow
    
    Args:
        message_id: Email message ID
        
    Returns:
        Success message
    """
    try:
        workflow = db_manager.get_workflow(message_id)
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        if workflow.current_state != "failed":
            raise HTTPException(
                status_code=400,
                detail=f"Workflow is not in failed state (current: {workflow.current_state})"
            )
        
        # Reset retry count and regenerate AI reply
        from app.models import WorkflowStateUpdate
        db_manager.update_workflow(
            message_id,
            WorkflowStateUpdate(
                current_state="pending",
                retry_count=0,
                error_message=None
            )
        )
        
        # Trigger workflow
        await workflow_manager.generate_ai_reply(message_id)
        
        return {"message": "Workflow retry initiated", "message_id": message_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying workflow {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow/timeout/{message_id}")
async def timeout_workflow(message_id: str):
    """
    Manually timeout a workflow
    
    Args:
        message_id: Email message ID
        
    Returns:
        Success message
    """
    try:
        workflow = db_manager.get_workflow(message_id)
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        if workflow.current_state != "awaiting_user":
            raise HTTPException(
                status_code=400,
                detail=f"Workflow is not awaiting user (current: {workflow.current_state})"
            )
        
        # Mark as timeout
        from app.models import WorkflowStateUpdate
        db_manager.update_workflow(
            message_id,
            WorkflowStateUpdate(current_state="timeout")
        )
        
        # Update email status
        await workflow_manager.email_monitor.update_email_status(message_id, "timeout")
        
        return {"message": "Workflow timed out", "message_id": message_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error timing out workflow {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/orchestrator/sms-response")
async def handle_sms_response(webhook: IncomingSMSWebhook):
    """
    Webhook endpoint for incoming SMS responses from user
    
    This is called by the SMS Gateway when the user sends an SMS.
    The SMS should contain a command (1/2/3) and optionally edit instructions.
    
    Args:
        webhook: Incoming SMS webhook payload
        
    Returns:
        Success message
    """
    try:
        logger.info(f"Received SMS webhook: {webhook.event}")
        
        # Extract SMS details
        phone_number = webhook.payload.phoneNumber
        message = webhook.payload.message
        
        logger.info(f"SMS from {phone_number}: {message}")
        
        # Verify it's from the user's phone
        your_phone_number = os.getenv('YOUR_PHONE_NUMBER', '')
        if phone_number != your_phone_number:
            logger.warning(f"SMS from unknown number: {phone_number}")
            return {"status": "ignored", "reason": "unknown phone number"}
        
        # Find workflow awaiting user response
        # We need to match the SMS to a workflow - for now, get the most recent awaiting_user workflow
        workflows = db_manager.get_workflows_by_state("awaiting_user", limit=1)
        
        if not workflows:
            logger.warning("No workflows awaiting user response")
            # Send help message
            from app.sms_client import get_sms_client
            sms_client = get_sms_client()
            await sms_client.send_sms(
                phone_number,
                "No pending emails. Commands: 1=Send 2=Edit 3=Ignore"
            )
            return {"status": "no_pending_workflows"}
        
        # Handle the most recent workflow
        workflow = workflows[0]
        await workflow_manager.handle_user_response(workflow.message_id, message)
        
        return {
            "status": "processed",
            "message_id": workflow.message_id,
            "command": message
        }
        
    except Exception as e:
        logger.error(f"Error handling SMS response: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Email Auto-Reply Orchestrator",
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8003"))
    
    uvicorn.run(app, host=host, port=port)
