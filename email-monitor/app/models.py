"""
Data models for Email Monitor service
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class EmailMessage(BaseModel):
    """Represents a parsed email message"""
    message_id: str
    subject: str
    from_address: EmailStr
    to_addresses: List[EmailStr]
    cc_addresses: Optional[List[EmailStr]] = []
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    received_at: datetime
    in_reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    is_read: bool = False


class EmailFilter(BaseModel):
    """Configuration for email filtering"""
    whitelist_senders: List[str] = Field(default_factory=list, description="Email addresses or domains to always process")
    blacklist_senders: List[str] = Field(default_factory=list, description="Email addresses or domains to always ignore")
    whitelist_subjects: List[str] = Field(default_factory=list, description="Subject keywords to always process")
    blacklist_subjects: List[str] = Field(default_factory=list, description="Subject keywords to always ignore")
    
    def should_process(self, email: EmailMessage) -> bool:
        """
        Determine if an email should be processed based on filter rules.
        
        Priority:
        1. Blacklist (if matched, reject)
        2. Whitelist (if matched, accept)
        3. Default behavior (accept if no rules match)
        """
        from_addr = email.from_address.lower()
        subject = email.subject.lower()
        
        # Check blacklist first (highest priority)
        for blocked in self.blacklist_senders:
            blocked = blocked.lower()
            if blocked.startswith('@'):  # Domain blacklist
                if from_addr.endswith(blocked):
                    return False
            elif from_addr == blocked or from_addr.endswith(f'<{blocked}>'):
                return False
        
        for blocked_keyword in self.blacklist_subjects:
            if blocked_keyword.lower() in subject:
                return False
        
        # Check whitelist
        if self.whitelist_senders:
            whitelist_match = False
            for allowed in self.whitelist_senders:
                allowed = allowed.lower()
                if allowed.startswith('@'):  # Domain whitelist
                    if from_addr.endswith(allowed):
                        whitelist_match = True
                        break
                elif from_addr == allowed or from_addr.endswith(f'<{allowed}>'):
                    whitelist_match = True
                    break
            
            if not whitelist_match:
                return False
        
        if self.whitelist_subjects:
            subject_match = False
            for keyword in self.whitelist_subjects:
                if keyword.lower() in subject:
                    subject_match = True
                    break
            
            if not subject_match:
                return False
        
        # Default: accept if no rules matched
        return True


class ProcessedEmail(BaseModel):
    """Tracks processed email state"""
    message_id: str
    processed_at: datetime
    status: str  # 'pending', 'sent', 'ignored', 'failed'
    reply_draft: Optional[str] = None
    error_message: Optional[str] = None
