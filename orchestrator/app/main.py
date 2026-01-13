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
from fastapi.responses import JSONResponse, HTMLResponse

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
        
        # Update email status in database
        db_manager.update_email_status(message_id, "timeout")
        
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


@app.get("/drafts/{message_id}", response_class=HTMLResponse)
async def get_draft(message_id: str):
    """
    Get draft email for review (mobile-friendly HTML)
    
    Security: message_id acts as secret token
    Expiry: Drafts expire 24h after creation (checked via workflow created_at)
    
    Args:
        message_id: Email message ID
        
    Returns:
        HTML page with draft email for review
    """
    try:
        from datetime import datetime, timezone, timedelta
        
        # Get workflow from database
        workflow = db_manager.get_workflow(message_id)
        
        if not workflow:
            return HTMLResponse(
                content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Draft Not Found</title>
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                               padding: 20px; background: #f5f5f5; }
                        .container { max-width: 600px; margin: 0 auto; background: white;
                                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                        h1 { color: #d32f2f; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>❌ Draft Not Found</h1>
                        <p>This draft does not exist or has been deleted.</p>
                    </div>
                </body>
                </html>
                """,
                status_code=404
            )
        
        # Check if draft has expired (24 hours from creation)
        expiry_time = workflow.created_at + timedelta(hours=24)
        if datetime.now(timezone.utc) > expiry_time:
            return HTMLResponse(
                content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Draft Expired</title>
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                               padding: 20px; background: #f5f5f5; }
                        .container { max-width: 600px; margin: 0 auto; background: white;
                                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                        h1 { color: #f57c00; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>⏰ Draft Expired</h1>
                        <p>This draft has expired (24 hour limit).</p>
                        <p>Please check your email for the latest status.</p>
                    </div>
                </body>
                </html>
                """,
                status_code=410
            )
        
        # Generate mobile-friendly HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Email Draft Review</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 16px;
                    background: #f5f5f5;
                    font-size: 16px;
                    line-height: 1.5;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: #1976d2;
                    color: white;
                    padding: 16px;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 20px;
                    font-weight: 600;
                }}
                .section {{
                    padding: 16px;
                    border-bottom: 1px solid #e0e0e0;
                }}
                .section:last-child {{
                    border-bottom: none;
                }}
                .section-title {{
                    font-size: 12px;
                    text-transform: uppercase;
                    color: #666;
                    margin: 0 0 8px 0;
                    font-weight: 600;
                }}
                .section-content {{
                    margin: 0;
                    color: #333;
                }}
                .email-from {{
                    font-weight: 600;
                    color: #1976d2;
                }}
                .email-subject {{
                    font-weight: 600;
                }}
                .email-body {{
                    background: #f9f9f9;
                    padding: 12px;
                    border-radius: 4px;
                    border-left: 3px solid #e0e0e0;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                .draft-reply {{
                    background: #e3f2fd;
                    padding: 12px;
                    border-radius: 4px;
                    border-left: 3px solid #1976d2;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                .actions {{
                    background: #fafafa;
                    padding: 16px;
                    text-align: center;
                }}
                .actions p {{
                    margin: 0 0 12px 0;
                    color: #666;
                    font-size: 14px;
                }}
                .action-codes {{
                    font-family: 'Courier New', monospace;
                    font-size: 18px;
                    font-weight: 600;
                    color: #333;
                    background: white;
                    padding: 12px;
                    border-radius: 4px;
                    border: 2px solid #e0e0e0;
                }}
                .status {{
                    padding: 16px;
                    background: #fff3e0;
                    text-align: center;
                }}
                .status-badge {{
                    display: inline-block;
                    padding: 6px 12px;
                    border-radius: 12px;
                    font-size: 12px;
                    font-weight: 600;
                    text-transform: uppercase;
                }}
                .status-awaiting {{
                    background: #ff9800;
                    color: white;
                }}
                .expiry {{
                    font-size: 12px;
                    color: #666;
                    text-align: center;
                    padding: 8px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📧 Email Draft Review</h1>
                </div>
                
                <div class="section">
                    <p class="section-title">From</p>
                    <p class="section-content email-from">{workflow.email_from or 'Unknown'}</p>
                </div>
                
                <div class="section">
                    <p class="section-title">Subject</p>
                    <p class="section-content email-subject">{workflow.email_subject or 'No Subject'}</p>
                </div>
                
                <div class="section">
                    <p class="section-title">Original Message</p>
                    <div class="email-body">{workflow.email_body_preview or 'No preview available'}</div>
                </div>
                
                <div class="section">
                    <p class="section-title">AI-Generated Draft Reply</p>
                    <div class="draft-reply">{workflow.ai_reply_text or 'No draft available'}</div>
                </div>
                
                <div class="status">
                    <span class="status-badge status-awaiting">⏳ {workflow.current_state.replace('_', ' ').title()}</span>
                </div>
                
                <div class="actions">
                    <p>Reply via SMS with:</p>
                    <div class="action-codes">
                        1 = Send<br>
                        2 = Edit<br>
                        3 = Ignore
                    </div>
                </div>
                
                <div class="expiry">
                    Draft expires: {expiry_time.strftime('%Y-%m-%d %H:%M UTC')}
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error retrieving draft {message_id}: {e}")
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Error</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                           padding: 20px; background: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: white;
                                padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    h1 {{ color: #d32f2f; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ Error</h1>
                    <p>An error occurred while retrieving the draft.</p>
                    <p style="color: #666; font-size: 14px;">{str(e)}</p>
                </div>
            </body>
            </html>
            """,
            status_code=500
        )


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
