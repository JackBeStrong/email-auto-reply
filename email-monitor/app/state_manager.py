"""
State management for tracking processed emails
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime
from threading import Lock

from .models import ProcessedEmail

logger = logging.getLogger(__name__)


class StateManager:
    """Manages state of processed emails to avoid reprocessing"""
    
    def __init__(self, state_file: str = "email_state.json"):
        self.state_file = Path(state_file)
        self.processed_emails: Dict[str, ProcessedEmail] = {}
        self.lock = Lock()
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from disk"""
        if not self.state_file.exists():
            logger.info("No existing state file found, starting fresh")
            return
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                
            for msg_id, email_data in data.items():
                # Convert datetime strings back to datetime objects
                email_data['processed_at'] = datetime.fromisoformat(email_data['processed_at'])
                self.processed_emails[msg_id] = ProcessedEmail(**email_data)
            
            logger.info(f"Loaded {len(self.processed_emails)} processed emails from state file")
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
            # Start fresh if state file is corrupted
            self.processed_emails = {}
    
    def _save_state(self) -> None:
        """Save state to disk"""
        try:
            # Convert to JSON-serializable format
            data = {}
            for msg_id, email in self.processed_emails.items():
                email_dict = email.model_dump()
                # Convert datetime to ISO format string
                email_dict['processed_at'] = email_dict['processed_at'].isoformat()
                data[msg_id] = email_dict
            
            # Write atomically by writing to temp file then renaming
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_file.replace(self.state_file)
            logger.debug(f"Saved state for {len(self.processed_emails)} emails")
        except Exception as e:
            logger.error(f"Error saving state file: {e}")
    
    def is_processed(self, message_id: str) -> bool:
        """Check if an email has already been processed"""
        with self.lock:
            return message_id in self.processed_emails
    
    def mark_processed(
        self,
        message_id: str,
        status: str = "pending",
        reply_draft: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Mark an email as processed"""
        with self.lock:
            processed_email = ProcessedEmail(
                message_id=message_id,
                processed_at=datetime.now(),
                status=status,
                reply_draft=reply_draft,
                error_message=error_message
            )
            self.processed_emails[message_id] = processed_email
            self._save_state()
            logger.debug(f"Marked email {message_id} as {status}")
    
    def update_status(
        self,
        message_id: str,
        status: str,
        reply_draft: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update the status of a processed email"""
        with self.lock:
            if message_id not in self.processed_emails:
                logger.warning(f"Cannot update status for untracked email {message_id}")
                return False
            
            email = self.processed_emails[message_id]
            email.status = status
            if reply_draft is not None:
                email.reply_draft = reply_draft
            if error_message is not None:
                email.error_message = error_message
            
            self._save_state()
            logger.debug(f"Updated email {message_id} status to {status}")
            return True
    
    def get_processed_email(self, message_id: str) -> Optional[ProcessedEmail]:
        """Get a processed email by message ID"""
        with self.lock:
            return self.processed_emails.get(message_id)
    
    def get_pending_emails(self) -> Dict[str, ProcessedEmail]:
        """Get all emails with pending status"""
        with self.lock:
            return {
                msg_id: email
                for msg_id, email in self.processed_emails.items()
                if email.status == "pending"
            }
    
    def get_processed_message_ids(self) -> Set[str]:
        """Get set of all processed message IDs"""
        with self.lock:
            return set(self.processed_emails.keys())
    
    def cleanup_old_entries(self, days: int = 30) -> int:
        """
        Remove entries older than specified days
        
        Args:
            days: Number of days to keep
            
        Returns:
            Number of entries removed
        """
        with self.lock:
            cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
            old_ids = [
                msg_id
                for msg_id, email in self.processed_emails.items()
                if email.processed_at.timestamp() < cutoff
            ]
            
            for msg_id in old_ids:
                del self.processed_emails[msg_id]
            
            if old_ids:
                self._save_state()
                logger.info(f"Cleaned up {len(old_ids)} old entries")
            
            return len(old_ids)
