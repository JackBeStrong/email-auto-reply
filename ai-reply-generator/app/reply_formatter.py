"""
Reply formatting and validation logic
"""
import os
import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Configuration from environment
SMS_FRIENDLY_MAX_LENGTH = int(os.getenv("SMS_FRIENDLY_MAX_LENGTH", "300"))
SUMMARY_MAX_LENGTH = int(os.getenv("SUMMARY_MAX_LENGTH", "150"))


class ReplyFormatter:
    """Handles reply formatting and validation"""
    
    # Profanity filter (basic list - expand as needed)
    PROFANITY_PATTERNS = [
        r'\bf[u\*]ck',
        r'\bsh[i\*]t',
        r'\bd[a\*]mn',
        r'\ba[s\*]s\b',
        r'\bb[i\*]tch',
    ]
    
    # Placeholder patterns to detect
    PLACEHOLDER_PATTERNS = [
        r'\[.*?\]',  # [Your Name], [Company], etc.
        r'\{.*?\}',  # {name}, {company}, etc.
        r'<.*?>',    # <name>, <company>, etc.
        r'XXX',
        r'TODO',
        r'FIXME',
    ]
    
    @staticmethod
    def is_sms_friendly(text: str) -> bool:
        """
        Check if text is short enough for SMS
        
        Args:
            text: Text to check
            
        Returns:
            True if text fits in SMS-friendly length
        """
        return len(text) <= SMS_FRIENDLY_MAX_LENGTH
    
    @staticmethod
    def validate_reply(text: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a reply draft
        
        Args:
            text: Reply text to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if empty
        if not text or not text.strip():
            return False, "Reply is empty"
        
        # Check minimum length (at least a few words)
        if len(text.strip()) < 10:
            return False, "Reply is too short (minimum 10 characters)"
        
        # Check maximum length (reasonable email reply)
        if len(text) > 5000:
            return False, "Reply is too long (maximum 5000 characters)"
        
        # Check for placeholders
        for pattern in ReplyFormatter.PLACEHOLDER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False, f"Reply contains placeholder: {pattern}"
        
        # Check for profanity (basic filter)
        for pattern in ReplyFormatter.PROFANITY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Reply contains potential profanity: {pattern}")
                # Don't fail validation, just log warning
        
        return True, None
    
    @staticmethod
    def detect_language(text: str) -> str:
        """
        Detect language of text (basic implementation)
        
        Args:
            text: Text to analyze
            
        Returns:
            Language code (e.g., 'en', 'unknown')
        """
        # Very basic detection - check for common English words
        english_words = ['the', 'is', 'are', 'was', 'were', 'have', 'has', 'will', 'would', 'can', 'could']
        text_lower = text.lower()
        
        english_count = sum(1 for word in english_words if f' {word} ' in f' {text_lower} ')
        
        if english_count >= 2:
            return 'en'
        
        return 'unknown'
    
    @staticmethod
    def format_for_sms(
        draft_id: str,
        email_from: str,
        email_subject: str,
        reply_text: str,
        is_sms_friendly: bool,
        short_summary: Optional[str] = None,
        web_url_base: Optional[str] = None
    ) -> str:
        """
        Format a reply for SMS notification
        
        Args:
            draft_id: Draft ID
            email_from: Sender email address
            email_subject: Email subject
            reply_text: Full reply text
            is_sms_friendly: Whether reply fits in SMS
            short_summary: Short summary (for long replies)
            web_url_base: Base URL for web interface (e.g., 'https://reply.jackan.xyz')
            
        Returns:
            Formatted SMS message
        """
        # Truncate email address if too long
        if len(email_from) > 30:
            email_from = email_from[:27] + "..."
        
        # Truncate subject if too long
        if len(email_subject) > 40:
            email_subject = email_subject[:37] + "..."
        
        if is_sms_friendly:
            # Short reply - include full text
            sms = f"From: {email_from}\n"
            sms += f"Re: {email_subject}\n\n"
            sms += f"Draft: \"{reply_text}\"\n\n"
            sms += f"1=Send 2=Edit 3=Ignore\n"
            sms += f"ID: #{draft_id}"
        else:
            # Long reply - include summary and link
            preview = short_summary or reply_text[:100] + "..."
            
            sms = f"From: {email_from}\n"
            sms += f"Re: {email_subject}\n\n"
            sms += f"Preview: \"{preview}\"\n\n"
            
            if web_url_base:
                sms += f"Full: {web_url_base}/d/{draft_id}\n"
            
            sms += f"1=Send 2=Edit 3=Ignore"
        
        return sms
    
    @staticmethod
    def extract_command(sms_text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract command from SMS response
        
        Args:
            sms_text: SMS text from user
            
        Returns:
            Tuple of (command, draft_id, edit_instruction) or (None, None, None) if not found
            
        Examples:
            "1" -> ("approve", None, None)
            "1 A7B2" -> ("approve", "A7B2", None)
            "2 make it more casual" -> ("edit", None, "make it more casual")
            "2 A7B2 make it shorter" -> ("edit", "A7B2", "make it shorter")
            "3" -> ("ignore", None, None)
        """
        sms_text = sms_text.strip()
        
        # Command mapping
        command_map = {
            '1': 'approve',
            '2': 'edit',
            '3': 'ignore',
            'approve': 'approve',
            'edit': 'edit',
            'ignore': 'ignore',
            'send': 'approve',
            'yes': 'approve',
            'no': 'ignore',
        }
        
        # Try to extract command, draft ID, and edit instruction
        parts = sms_text.split(maxsplit=2)  # Split into max 3 parts
        
        if not parts:
            return None, None, None
        
        # First part should be command
        command_str = parts[0].lower()
        command = command_map.get(command_str)
        
        if not command:
            return None, None, None
        
        # Parse remaining parts
        draft_id = None
        edit_instruction = None
        
        if len(parts) > 1:
            # Check if second part is a draft ID (8 alphanumeric chars)
            potential_id = parts[1].replace('#', '').upper()
            
            if len(potential_id) == 8 and potential_id.isalnum():
                # It's a draft ID
                draft_id = potential_id
                
                # Third part might be edit instruction
                if len(parts) > 2:
                    edit_instruction = parts[2].strip()
            else:
                # Second part is not a draft ID, treat as edit instruction
                # Rejoin parts 1 and 2 as the instruction
                edit_instruction = ' '.join(parts[1:]).strip()
        
        return command, draft_id, edit_instruction
    
    @staticmethod
    def clean_reply_text(text: str) -> str:
        """
        Clean and normalize reply text
        
        Args:
            text: Raw reply text
            
        Returns:
            Cleaned text
        """
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Normalize line breaks (max 2 consecutive)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove excessive spaces
        text = re.sub(r' {2,}', ' ', text)
        
        # Remove leading/trailing spaces on each line
        lines = text.split('\n')
        text = '\n'.join(line.strip() for line in lines)
        
        return text
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count for text (rough approximation)
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated token count
        """
        # Rough estimate: ~4 characters per token for English
        return len(text) // 4
