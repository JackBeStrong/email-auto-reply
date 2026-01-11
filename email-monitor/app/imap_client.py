"""
IMAP client for monitoring Gmail inbox
"""
import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import List, Optional, Tuple
import logging
from datetime import datetime

from .models import EmailMessage

logger = logging.getLogger(__name__)


class IMAPClient:
    """Client for connecting to Gmail via IMAP and fetching emails"""
    
    def __init__(
        self,
        imap_server: str,
        email_address: str,
        password: str,
        port: int = 993
    ):
        self.imap_server = imap_server
        self.email_address = email_address
        self.password = password
        self.port = port
        self.connection: Optional[imaplib.IMAP4_SSL] = None
    
    def connect(self) -> None:
        """Establish connection to IMAP server"""
        try:
            logger.info(f"Connecting to {self.imap_server}:{self.port}")
            self.connection = imaplib.IMAP4_SSL(self.imap_server, self.port)
            self.connection.login(self.email_address, self.password)
            logger.info("Successfully connected to IMAP server")
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close connection to IMAP server"""
        if self.connection:
            try:
                self.connection.logout()
                logger.info("Disconnected from IMAP server")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self.connection = None
    
    def select_mailbox(self, mailbox: str = "INBOX") -> None:
        """Select a mailbox to work with"""
        if not self.connection:
            raise RuntimeError("Not connected to IMAP server")
        
        status, messages = self.connection.select(mailbox)
        if status != "OK":
            raise RuntimeError(f"Failed to select mailbox {mailbox}")
        
        logger.debug(f"Selected mailbox: {mailbox}")
    
    def fetch_unread_emails(self, limit: int = 10) -> List[EmailMessage]:
        """
        Fetch unread emails from the inbox
        
        Args:
            limit: Maximum number of emails to fetch
            
        Returns:
            List of EmailMessage objects
        """
        if not self.connection:
            raise RuntimeError("Not connected to IMAP server")
        
        self.select_mailbox("INBOX")
        
        # Search for unread emails
        status, message_ids = self.connection.search(None, "UNSEEN")
        if status != "OK":
            logger.error("Failed to search for unread emails")
            return []
        
        # Get list of message IDs
        id_list = message_ids[0].split()
        if not id_list:
            logger.debug("No unread emails found")
            return []
        
        # Limit the number of emails to fetch
        id_list = id_list[-limit:] if len(id_list) > limit else id_list
        
        emails = []
        for msg_id in id_list:
            try:
                email_msg = self._fetch_email_by_id(msg_id)
                if email_msg:
                    emails.append(email_msg)
            except Exception as e:
                logger.error(f"Error fetching email {msg_id}: {e}")
                continue
        
        logger.info(f"Fetched {len(emails)} unread emails")
        return emails
    
    def _fetch_email_by_id(self, msg_id: bytes) -> Optional[EmailMessage]:
        """Fetch and parse a single email by ID"""
        if not self.connection:
            raise RuntimeError("Not connected to IMAP server")
        
        # Fetch the email
        status, msg_data = self.connection.fetch(msg_id, "(RFC822)")
        if status != "OK":
            logger.error(f"Failed to fetch email {msg_id}")
            return None
        
        # Parse the email
        raw_email = msg_data[0][1]
        email_message = email.message_from_bytes(raw_email)
        
        return self._parse_email(email_message)
    
    def _parse_email(self, email_message: email.message.Message) -> EmailMessage:
        """Parse email.message.Message into our EmailMessage model"""
        
        # Get message ID
        message_id = email_message.get("Message-ID", "")
        
        # Get subject
        subject = self._decode_header(email_message.get("Subject", ""))
        
        # Get from address
        from_header = email_message.get("From", "")
        from_name, from_address = parseaddr(from_header)
        
        # Get to addresses
        to_header = email_message.get("To", "")
        to_addresses = [addr for name, addr in [parseaddr(to_header)]]
        
        # Get CC addresses
        cc_header = email_message.get("Cc", "")
        cc_addresses = []
        if cc_header:
            cc_addresses = [addr for name, addr in [parseaddr(cc_header)]]
        
        # Get date
        date_header = email_message.get("Date")
        try:
            received_at = parsedate_to_datetime(date_header) if date_header else datetime.now()
        except Exception:
            received_at = datetime.now()
        
        # Get In-Reply-To for threading
        in_reply_to = email_message.get("In-Reply-To")
        
        # Get References for threading (use first reference as thread_id)
        references = email_message.get("References")
        thread_id = references.split()[0] if references else message_id
        
        # Extract body
        body_text, body_html = self._extract_body(email_message)
        
        return EmailMessage(
            message_id=message_id,
            subject=subject,
            from_address=from_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            in_reply_to=in_reply_to,
            thread_id=thread_id,
            is_read=False
        )
    
    def _decode_header(self, header: str) -> str:
        """Decode email header that might be encoded"""
        if not header:
            return ""
        
        decoded_parts = []
        for part, encoding in decode_header(header):
            if isinstance(part, bytes):
                decoded_parts.append(
                    part.decode(encoding or "utf-8", errors="replace")
                )
            else:
                decoded_parts.append(part)
        
        return "".join(decoded_parts)
    
    def _extract_body(self, email_message: email.message.Message) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract text and HTML body from email
        
        Returns:
            Tuple of (text_body, html_body)
        """
        body_text = None
        body_html = None
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # Skip attachments
                if "attachment" in content_disposition:
                    continue
                
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        decoded_payload = payload.decode(charset, errors="replace")
                        
                        if content_type == "text/plain" and not body_text:
                            body_text = decoded_payload
                        elif content_type == "text/html" and not body_html:
                            body_html = decoded_payload
                except Exception as e:
                    logger.warning(f"Error decoding email part: {e}")
                    continue
        else:
            # Not multipart - single body
            content_type = email_message.get_content_type()
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    charset = email_message.get_content_charset() or "utf-8"
                    decoded_payload = payload.decode(charset, errors="replace")
                    
                    if content_type == "text/plain":
                        body_text = decoded_payload
                    elif content_type == "text/html":
                        body_html = decoded_payload
            except Exception as e:
                logger.warning(f"Error decoding email body: {e}")
        
        return body_text, body_html
    
    def mark_as_read(self, message_id: str) -> bool:
        """Mark an email as read"""
        if not self.connection:
            raise RuntimeError("Not connected to IMAP server")
        
        try:
            # Search for the message by Message-ID
            status, msg_ids = self.connection.search(None, f'HEADER Message-ID "{message_id}"')
            if status != "OK" or not msg_ids[0]:
                logger.warning(f"Could not find message {message_id}")
                return False
            
            msg_id = msg_ids[0].split()[0]
            
            # Mark as seen
            self.connection.store(msg_id, "+FLAGS", "\\Seen")
            logger.debug(f"Marked message {message_id} as read")
            return True
        except Exception as e:
            logger.error(f"Error marking message as read: {e}")
            return False
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
