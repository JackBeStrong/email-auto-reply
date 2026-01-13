"""
Workflow Manager

Orchestrates the entire email auto-reply workflow:
1. Poll Email Monitor for pending emails
2. Request AI-generated replies
3. Send SMS notifications
4. Handle user responses (approve/edit/ignore)
5. Send approved replies via Gmail
"""
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.database import DatabaseManager, get_database_manager
from app.email_monitor_client import EmailMonitorClient, get_email_monitor_client
from app.ai_reply_client import AIReplyClient, get_ai_reply_client
from app.sms_client import SMSClient, get_sms_client, format_sms_notification
from app.gmail_client import GmailClient, get_gmail_client
from app.command_parser import CommandParser
from app.models import (
    WorkflowStateCreate,
    WorkflowStateUpdate,
    EmailDetail,
    ParsedCommand
)

logger = logging.getLogger(__name__)


class WorkflowManager:
    """Manages the email auto-reply workflow"""
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        email_monitor: EmailMonitorClient,
        ai_reply: AIReplyClient,
        sms: SMSClient,
        gmail: GmailClient,
        your_phone_number: str,
        user_response_timeout: int = 86400,  # 24 hours
        max_edit_iterations: int = 10,
        max_retry_attempts: int = 3,
        max_emails_per_poll: int = 5  # Safety limit
    ):
        """
        Initialize workflow manager.
        
        Args:
            db_manager: Database manager
            email_monitor: Email Monitor client
            ai_reply: AI Reply Generator client
            sms: SMS Gateway client
            gmail: Gmail SMTP client
            your_phone_number: User's phone number for SMS
            user_response_timeout: Timeout for user response in seconds
            max_edit_iterations: Maximum number of edit iterations
            max_retry_attempts: Maximum retry attempts for failures
            max_emails_per_poll: Maximum emails to process per poll cycle
        """
        self.db = db_manager
        self.email_monitor = email_monitor
        self.ai_reply = ai_reply
        self.sms = sms
        self.gmail = gmail
        self.your_phone_number = your_phone_number
        self.user_response_timeout = user_response_timeout
        self.max_edit_iterations = max_edit_iterations
        self.max_retry_attempts = max_retry_attempts
        self.max_emails_per_poll = max_emails_per_poll
        self.command_parser = CommandParser()
    
    async def process_pending_emails(self):
        """
        Poll Email Monitor for pending emails and start workflow for each.
        """
        try:
            logger.info("Polling Email Monitor for pending emails...")
            pending_emails = await self.email_monitor.get_pending_emails()
            
            if not pending_emails:
                logger.debug("No pending emails found")
                return
            
            logger.info(f"Found {len(pending_emails)} pending emails")
            
            # Safety limit to prevent SMS bombardment
            processed_count = 0
            for email in pending_emails:
                # Check if workflow already exists
                if self.db.workflow_exists(email.message_id):
                    logger.debug(f"Workflow already exists for {email.message_id}")
                    continue
                
                # Check if we've hit the limit
                if processed_count >= self.max_emails_per_poll:
                    logger.warning(f"Reached max emails per poll limit ({self.max_emails_per_poll}), skipping remaining emails")
                    break
                
                # Start workflow for this email
                await self.start_workflow(email)
                processed_count += 1
                
        except Exception as e:
            logger.error(f"Error processing pending emails: {e}")
    
    async def start_workflow(self, email: EmailDetail):
        """
        Start workflow for a new email.
        
        Args:
            email: Email details from Email Monitor
        """
        try:
            logger.info(f"Starting workflow for email {email.message_id}")
            
            # Create workflow state
            timeout_at = datetime.utcnow() + timedelta(seconds=self.user_response_timeout)
            # Convert to_addresses list to comma-separated string
            to_address = ", ".join(email.to_addresses) if email.to_addresses else ""
            workflow = WorkflowStateCreate(
                message_id=email.message_id,
                email_subject=email.subject,
                email_from=email.from_address,
                email_to=to_address,
                email_body_preview=email.body_text[:200] if email.body_text else "",
                current_state="pending",
                timeout_at=timeout_at
            )
            
            self.db.create_workflow(workflow)
            
            # Update email status in Email Monitor
            await self.email_monitor.update_email_status(email.message_id, "orchestrating")
            
            # Generate AI reply
            await self.generate_ai_reply(email.message_id)
            
        except Exception as e:
            logger.error(f"Error starting workflow for {email.message_id}: {e}")
            await self.handle_workflow_error(email.message_id, "start_workflow", str(e))
    
    async def generate_ai_reply(self, message_id: str, edit_instructions: Optional[str] = None):
        """
        Generate AI reply for an email.
        
        Args:
            message_id: Email message ID
            edit_instructions: Optional edit instructions from user
        """
        try:
            # Update state to ai_generating
            self.db.update_workflow(
                message_id,
                WorkflowStateUpdate(
                    current_state="ai_generating",
                    previous_state="pending" if not edit_instructions else "awaiting_user"
                )
            )
            
            logger.info(f"Generating AI reply for {message_id}")
            if edit_instructions:
                logger.info(f"Edit instructions: {edit_instructions}")
            
            # Request AI reply
            ai_response = await self.ai_reply.generate_reply(message_id, edit_instructions)
            
            if not ai_response:
                raise Exception("AI reply generation failed")
            
            # Update workflow with AI reply
            self.db.update_workflow(
                message_id,
                WorkflowStateUpdate(
                    current_state="ai_generated",
                    ai_reply_text=ai_response.reply_text,
                    ai_reply_generated_at=datetime.utcnow()
                )
            )
            
            # Send SMS notification
            await self.send_sms_notification(message_id)
            
        except Exception as e:
            logger.error(f"Error generating AI reply for {message_id}: {e}")
            await self.handle_workflow_error(message_id, "generate_ai_reply", str(e))
    
    async def send_sms_notification(self, message_id: str):
        """
        Send SMS notification with email details and AI reply.
        
        Args:
            message_id: Email message ID
        """
        try:
            # Get workflow state
            workflow = self.db.get_workflow(message_id)
            if not workflow:
                raise Exception(f"Workflow not found for {message_id}")
            
            # Update state to sms_sending
            self.db.update_workflow(
                message_id,
                WorkflowStateUpdate(current_state="sms_sending")
            )
            
            # Format SMS message
            sms_format = os.getenv('SMS_FORMAT', 'condensed')
            sms_message = format_sms_notification(
                email_from=workflow.email_from or "Unknown",
                email_subject=workflow.email_subject or "No subject",
                email_body_preview=workflow.email_body_preview or "",
                ai_reply=workflow.ai_reply_text or "",
                format_type=sms_format
            )
            
            logger.info(f"Sending SMS notification for {message_id}")
            
            # Send SMS
            sms_response = await self.sms.send_sms(self.your_phone_number, sms_message)
            
            if not sms_response or not sms_response.success:
                raise Exception(f"SMS sending failed: {sms_response.error if sms_response else 'Unknown error'}")
            
            # Update workflow state
            self.db.update_workflow(
                message_id,
                WorkflowStateUpdate(
                    current_state="awaiting_user",
                    sms_message_id=sms_response.message_id,
                    sms_sent_at=datetime.utcnow(),
                    sms_phone_number=self.your_phone_number
                )
            )
            
            logger.info(f"SMS sent successfully for {message_id}, awaiting user response")
            
        except Exception as e:
            logger.error(f"Error sending SMS notification for {message_id}: {e}")
            await self.handle_workflow_error(message_id, "send_sms_notification", str(e))
    
    async def handle_user_response(self, message_id: str, user_message: str):
        """
        Handle user SMS response (approve/edit/ignore).
        
        Args:
            message_id: Email message ID
            user_message: User's SMS message
        """
        try:
            # Get workflow state
            workflow = self.db.get_workflow(message_id)
            if not workflow:
                logger.error(f"Workflow not found for {message_id}")
                return
            
            # Check if workflow is awaiting user response
            if workflow.current_state != "awaiting_user":
                logger.warning(f"Workflow {message_id} not awaiting user response (state: {workflow.current_state})")
                return
            
            # Parse command
            parsed = self.command_parser.parse(user_message)
            logger.info(f"User command for {message_id}: {parsed.command_type}")
            
            # Update workflow with user response
            self.db.update_workflow(
                message_id,
                WorkflowStateUpdate(
                    user_command=parsed.command_type,
                    user_responded_at=datetime.utcnow()
                )
            )
            
            # Handle command
            if parsed.command_type == 'approve':
                await self.send_email_reply(message_id)
            
            elif parsed.command_type == 'edit':
                # Check edit iteration limit
                if workflow.edit_iteration >= self.max_edit_iterations:
                    logger.warning(f"Max edit iterations reached for {message_id}")
                    await self.sms.send_sms(
                        self.your_phone_number,
                        f"⚠️ Max edits reached for this email. Please approve (1) or ignore (3)."
                    )
                    return
                
                # Increment edit iteration
                self.db.update_workflow(
                    message_id,
                    WorkflowStateUpdate(
                        edit_iteration=workflow.edit_iteration + 1,
                        user_edit_instructions=parsed.edit_instructions
                    )
                )
                
                # Regenerate AI reply with edit instructions
                await self.generate_ai_reply(message_id, parsed.edit_instructions)
            
            elif parsed.command_type == 'ignore':
                await self.ignore_email(message_id)
            
            else:
                # Unknown command
                logger.warning(f"Unknown command from user: {user_message}")
                help_text = self.command_parser.get_help_text()
                await self.sms.send_sms(self.your_phone_number, f"❓ Unknown command.\n{help_text}")
            
        except Exception as e:
            logger.error(f"Error handling user response for {message_id}: {e}")
            await self.handle_workflow_error(message_id, "handle_user_response", str(e))
    
    async def send_email_reply(self, message_id: str):
        """
        Send email reply via Gmail SMTP.
        
        Args:
            message_id: Email message ID
        """
        try:
            # Get workflow state
            workflow = self.db.get_workflow(message_id)
            if not workflow:
                raise Exception(f"Workflow not found for {message_id}")
            
            # Get email details
            email = await self.email_monitor.get_email_details(message_id)
            if not email:
                raise Exception(f"Email details not found for {message_id}")
            
            logger.info(f"Sending email reply for {message_id}")
            
            # Send reply via Gmail
            reply_message_id = self.gmail.send_reply(
                to=email.from_address,
                subject=email.subject or "No subject",
                body=workflow.ai_reply_text or "",
                in_reply_to=email.in_reply_to,
                references=email.references
            )
            
            # Update workflow state
            self.db.update_workflow(
                message_id,
                WorkflowStateUpdate(
                    current_state="reply_sent",
                    reply_sent_at=datetime.utcnow(),
                    reply_message_id=reply_message_id
                )
            )
            
            # Update email status in Email Monitor
            await self.email_monitor.update_email_status(message_id, "sent")
            
            logger.info(f"Email reply sent successfully for {message_id}")
            
            # Send confirmation SMS
            await self.sms.send_sms(
                self.your_phone_number,
                f"✅ Reply sent to {email.from_address.split('@')[0]}"
            )
            
        except Exception as e:
            logger.error(f"Error sending email reply for {message_id}: {e}")
            await self.handle_workflow_error(message_id, "send_email_reply", str(e))
            
            # Notify user of failure
            await self.sms.send_sms(
                self.your_phone_number,
                f"❌ Failed to send reply. Error: {str(e)[:100]}"
            )
    
    async def ignore_email(self, message_id: str):
        """
        Mark email as ignored.
        
        Args:
            message_id: Email message ID
        """
        try:
            logger.info(f"Ignoring email {message_id}")
            
            # Update workflow state
            self.db.update_workflow(
                message_id,
                WorkflowStateUpdate(current_state="user_ignored")
            )
            
            # Update email status in Email Monitor
            await self.email_monitor.update_email_status(message_id, "ignored")
            
            # Send confirmation SMS
            await self.sms.send_sms(
                self.your_phone_number,
                "✓ Email ignored"
            )
            
        except Exception as e:
            logger.error(f"Error ignoring email {message_id}: {e}")
    
    async def handle_workflow_error(self, message_id: str, stage: str, error: str):
        """
        Handle workflow error with retry logic.
        
        Args:
            message_id: Email message ID
            stage: Stage where error occurred
            error: Error message
        """
        try:
            workflow = self.db.get_workflow(message_id)
            if not workflow:
                logger.error(f"Cannot handle error: workflow not found for {message_id}")
                return
            
            retry_count = workflow.retry_count + 1
            
            if retry_count <= self.max_retry_attempts:
                logger.info(f"Retrying workflow for {message_id} (attempt {retry_count}/{self.max_retry_attempts})")
                
                # Update retry count
                self.db.update_workflow(
                    message_id,
                    WorkflowStateUpdate(
                        retry_count=retry_count,
                        error_message=f"{stage}: {error}"
                    )
                )
                
                # Retry based on stage
                if stage in ["start_workflow", "generate_ai_reply"]:
                    await asyncio.sleep(5 * retry_count)  # Exponential backoff
                    await self.generate_ai_reply(message_id)
                elif stage == "send_sms_notification":
                    await asyncio.sleep(5 * retry_count)
                    await self.send_sms_notification(message_id)
                elif stage == "send_email_reply":
                    await asyncio.sleep(5 * retry_count)
                    await self.send_email_reply(message_id)
            else:
                logger.error(f"Max retries exceeded for {message_id}, marking as failed")
                
                # Mark as failed
                self.db.update_workflow(
                    message_id,
                    WorkflowStateUpdate(
                        current_state="failed",
                        error_message=f"{stage}: {error} (max retries exceeded)"
                    )
                )
                
                # Notify user
                await self.sms.send_sms(
                    self.your_phone_number,
                    f"⚠️ Workflow failed for email {message_id[:20]}... Error: {error[:50]}"
                )
                
        except Exception as e:
            logger.error(f"Error handling workflow error for {message_id}: {e}")
    
    async def check_timeouts(self):
        """
        Check for workflows that have timed out and handle them.
        """
        try:
            timed_out = self.db.get_timed_out_workflows()
            
            if not timed_out:
                return
            
            logger.info(f"Found {len(timed_out)} timed out workflows")
            
            for workflow in timed_out:
                logger.info(f"Handling timeout for {workflow.message_id}")
                
                # Update state to timeout
                self.db.update_workflow(
                    workflow.message_id,
                    WorkflowStateUpdate(current_state="timeout")
                )
                
                # Update email status
                await self.email_monitor.update_email_status(workflow.message_id, "timeout")
                
                # Optionally send reminder SMS
                # await self.sms.send_sms(
                #     self.your_phone_number,
                #     f"⏰ Email from {workflow.email_from} timed out (no response)"
                # )
                
        except Exception as e:
            logger.error(f"Error checking timeouts: {e}")


def get_workflow_manager() -> WorkflowManager:
    """
    Get workflow manager instance from environment.
    
    Returns:
        WorkflowManager instance
    """
    db_manager = get_database_manager()
    email_monitor = get_email_monitor_client()
    ai_reply = get_ai_reply_client()
    sms = get_sms_client()
    gmail = get_gmail_client()
    
    your_phone_number = os.getenv('YOUR_PHONE_NUMBER', '')
    if not your_phone_number:
        raise ValueError("YOUR_PHONE_NUMBER must be set in environment")
    
    user_response_timeout = int(os.getenv('USER_RESPONSE_TIMEOUT', '86400'))
    max_edit_iterations = int(os.getenv('MAX_EDIT_ITERATIONS', '10'))
    max_retry_attempts = int(os.getenv('MAX_RETRY_ATTEMPTS', '3'))
    max_emails_per_poll = int(os.getenv('MAX_EMAILS_PER_POLL', '5'))
    
    return WorkflowManager(
        db_manager=db_manager,
        email_monitor=email_monitor,
        ai_reply=ai_reply,
        sms=sms,
        gmail=gmail,
        your_phone_number=your_phone_number,
        user_response_timeout=user_response_timeout,
        max_edit_iterations=max_edit_iterations,
        max_retry_attempts=max_retry_attempts,
        max_emails_per_poll=max_emails_per_poll
    )
