"""
Database module using SQLAlchemy ORM for PostgreSQL integration
"""
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta

from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, TIMESTAMP, ARRAY, ForeignKey, Index, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import INET

from .models import ProcessedEmail, EmailFilter

logger = logging.getLogger(__name__)

Base = declarative_base()


# ============================================================================
# SQLAlchemy Models
# ============================================================================

class ProcessedEmailDB(Base):
    """Database model for processed emails"""
    __tablename__ = 'processed_emails'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(String(255), unique=True, nullable=False, index=True)
    subject = Column(Text)
    from_address = Column(String(255), nullable=False, index=True)
    to_addresses = Column(ARRAY(Text))
    body_text = Column(Text)
    body_html = Column(Text)
    received_at = Column(TIMESTAMP(timezone=True), nullable=False)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, index=True)
    status = Column(String(50), nullable=False, default='pending', index=True)
    reply_draft = Column(Text)
    error_message = Column(Text)
    thread_id = Column(String(255), index=True)
    in_reply_to = Column(String(255))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, index=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, onupdate=datetime.now)


class EmailFilterRuleDB(Base):
    """Database model for email filter rules"""
    __tablename__ = 'email_filter_rules'
    
    id = Column(Integer, primary_key=True)
    rule_type = Column(String(50), nullable=False, index=True)
    pattern = Column(String(500), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, index=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, onupdate=datetime.now)
    
    __table_args__ = (
        Index('idx_filter_rules_type', 'rule_type'),
        Index('idx_filter_rules_active', 'is_active'),
    )


class SMSNotificationDB(Base):
    """Database model for SMS notifications"""
    __tablename__ = 'sms_notifications'
    
    id = Column(Integer, primary_key=True)
    email_message_id = Column(String(255), ForeignKey('processed_emails.message_id', ondelete='CASCADE'), nullable=False, index=True)
    phone_number = Column(String(20), nullable=False)
    message_text = Column(Text, nullable=False)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, index=True)
    status = Column(String(50), nullable=False, default='sent', index=True)
    response_received_at = Column(TIMESTAMP(timezone=True))
    user_response = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, index=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, onupdate=datetime.now)


class AuditLogDB(Base):
    """Database model for audit log"""
    __tablename__ = 'audit_log'
    
    id = Column(Integer, primary_key=True)
    event_type = Column(String(100), nullable=False, index=True)
    event_data = Column(JSON)
    user_id = Column(String(100))
    ip_address = Column(INET)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, index=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.now, onupdate=datetime.now)


# ============================================================================
# Database Manager
# ============================================================================

class DatabaseManager:
    """Manages database operations using SQLAlchemy ORM"""
    
    def __init__(self, database_url: str):
        """
        Initialize database manager
        
        Args:
            database_url: PostgreSQL connection string
                         e.g., postgresql://user:password@host:port/database
        """
        self.engine = create_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=False  # Set to True for SQL query logging
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        logger.info(f"Database engine created: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def close(self):
        """Close database engine"""
        self.engine.dispose()
        logger.info("Database engine disposed")
    
    # ========================================================================
    # Processed Emails Operations
    # ========================================================================
    
    def is_processed(self, message_id: str) -> bool:
        """Check if an email has already been processed"""
        with self.get_session() as session:
            return session.query(ProcessedEmailDB).filter_by(message_id=message_id).first() is not None
    
    def mark_processed(
        self,
        message_id: str,
        subject: str,
        from_address: str,
        to_addresses: List[str],
        received_at: datetime,
        status: str = "pending",
        reply_draft: Optional[str] = None,
        error_message: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None
    ) -> int:
        """
        Mark an email as processed
        
        Returns:
            The ID of the inserted/updated record
        """
        with self.get_session() as session:
            # Check if already exists
            existing = session.query(ProcessedEmailDB).filter_by(message_id=message_id).first()
            
            if existing:
                # Update existing
                existing.status = status
                existing.reply_draft = reply_draft
                existing.error_message = error_message
                if body_text is not None:
                    existing.body_text = body_text
                if body_html is not None:
                    existing.body_html = body_html
                existing.updated_at = datetime.now()
                session.commit()
                email_id = existing.id
                logger.debug(f"Updated email {message_id} to status {status} (id: {email_id})")
            else:
                # Insert new
                email = ProcessedEmailDB(
                    message_id=message_id,
                    subject=subject,
                    from_address=from_address,
                    to_addresses=to_addresses,
                    body_text=body_text,
                    body_html=body_html,
                    received_at=received_at,
                    status=status,
                    reply_draft=reply_draft,
                    error_message=error_message,
                    thread_id=thread_id,
                    in_reply_to=in_reply_to
                )
                session.add(email)
                session.commit()
                email_id = email.id
                logger.debug(f"Marked email {message_id} as {status} (id: {email_id})")
            
            return email_id
    
    def update_status(
        self,
        message_id: str,
        status: str,
        reply_draft: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update the status of a processed email"""
        with self.get_session() as session:
            email = session.query(ProcessedEmailDB).filter_by(message_id=message_id).first()
            
            if not email:
                logger.warning(f"Cannot update status for untracked email {message_id}")
                return False
            
            email.status = status
            if reply_draft is not None:
                email.reply_draft = reply_draft
            if error_message is not None:
                email.error_message = error_message
            email.updated_at = datetime.now()
            
            session.commit()
            logger.debug(f"Updated email {message_id} status to {status}")
            return True
    
    def get_processed_email(self, message_id: str) -> Optional[ProcessedEmail]:
        """Get a processed email by message ID"""
        with self.get_session() as session:
            email = session.query(ProcessedEmailDB).filter_by(message_id=message_id).first()
            
            if email:
                return ProcessedEmail(
                    message_id=email.message_id,
                    processed_at=email.processed_at,
                    status=email.status,
                    reply_draft=email.reply_draft,
                    error_message=email.error_message
                )
            return None
    
    def get_pending_emails(self) -> Dict[str, ProcessedEmail]:
        """Get all emails with pending status"""
        with self.get_session() as session:
            emails = session.query(ProcessedEmailDB).filter_by(status='pending').order_by(ProcessedEmailDB.processed_at.desc()).all()
            
            return {
                email.message_id: ProcessedEmail(
                    message_id=email.message_id,
                    processed_at=email.processed_at,
                    status=email.status,
                    reply_draft=email.reply_draft,
                    error_message=email.error_message
                )
                for email in emails
            }
    
    def get_all_processed_emails(self, limit: int = 100) -> Dict[str, ProcessedEmail]:
        """Get all processed emails"""
        with self.get_session() as session:
            emails = session.query(ProcessedEmailDB).order_by(ProcessedEmailDB.processed_at.desc()).limit(limit).all()
            
            return {
                email.message_id: ProcessedEmail(
                    message_id=email.message_id,
                    processed_at=email.processed_at,
                    status=email.status,
                    reply_draft=email.reply_draft,
                    error_message=email.error_message
                )
                for email in emails
            }
    
    def get_processed_message_ids(self) -> Set[str]:
        """Get set of all processed message IDs"""
        with self.get_session() as session:
            message_ids = session.query(ProcessedEmailDB.message_id).all()
            return {msg_id[0] for msg_id in message_ids}
    
    def cleanup_old_entries(self, days: int = 30) -> int:
        """
        Remove entries older than specified days
        
        Args:
            days: Number of days to keep
            
        Returns:
            Number of entries removed
        """
        cutoff = datetime.now() - timedelta(days=days)
        with self.get_session() as session:
            deleted = session.query(ProcessedEmailDB).filter(ProcessedEmailDB.processed_at < cutoff).delete()
            session.commit()
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old entries")
            return deleted
    
    # ========================================================================
    # Email Filter Rules Operations
    # ========================================================================
    
    def get_filter_rules(self) -> EmailFilter:
        """Load email filter rules from database"""
        with self.get_session() as session:
            rules = session.query(EmailFilterRuleDB).filter_by(is_active=True).order_by(EmailFilterRuleDB.rule_type, EmailFilterRuleDB.pattern).all()
            
            whitelist_senders = []
            blacklist_senders = []
            whitelist_subjects = []
            blacklist_subjects = []
            
            for rule in rules:
                if rule.rule_type == 'whitelist_sender':
                    whitelist_senders.append(rule.pattern)
                elif rule.rule_type == 'blacklist_sender':
                    blacklist_senders.append(rule.pattern)
                elif rule.rule_type == 'whitelist_subject':
                    whitelist_subjects.append(rule.pattern)
                elif rule.rule_type == 'blacklist_subject':
                    blacklist_subjects.append(rule.pattern)
            
            logger.info(f"Loaded filter rules: {len(whitelist_senders)} whitelist senders, "
                       f"{len(blacklist_senders)} blacklist senders, "
                       f"{len(whitelist_subjects)} whitelist subjects, "
                       f"{len(blacklist_subjects)} blacklist subjects")
            
            return EmailFilter(
                whitelist_senders=whitelist_senders,
                blacklist_senders=blacklist_senders,
                whitelist_subjects=whitelist_subjects,
                blacklist_subjects=blacklist_subjects
            )
    
    def add_filter_rule(
        self,
        rule_type: str,
        pattern: str,
        description: Optional[str] = None
    ) -> int:
        """Add a new filter rule"""
        with self.get_session() as session:
            # Check if rule already exists
            existing = session.query(EmailFilterRuleDB).filter_by(rule_type=rule_type, pattern=pattern).first()
            
            if existing:
                # Reactivate if inactive
                existing.is_active = True
                existing.description = description
                existing.updated_at = datetime.now()
                session.commit()
                rule_id = existing.id
                logger.info(f"Reactivated filter rule: {rule_type} - {pattern}")
            else:
                # Create new
                rule = EmailFilterRuleDB(
                    rule_type=rule_type,
                    pattern=pattern,
                    description=description
                )
                session.add(rule)
                session.commit()
                rule_id = rule.id
                logger.info(f"Added filter rule: {rule_type} - {pattern}")
            
            return rule_id
    
    def remove_filter_rule(self, rule_id: int) -> bool:
        """Remove a filter rule (soft delete by setting is_active=false)"""
        with self.get_session() as session:
            rule = session.query(EmailFilterRuleDB).filter_by(id=rule_id).first()
            
            if not rule:
                return False
            
            rule.is_active = False
            rule.updated_at = datetime.now()
            session.commit()
            logger.info(f"Removed filter rule id: {rule_id}")
            return True
    
    def get_all_filter_rules(self, include_inactive: bool = False) -> List[Dict]:
        """Get all filter rules"""
        with self.get_session() as session:
            query = session.query(EmailFilterRuleDB)
            
            if not include_inactive:
                query = query.filter_by(is_active=True)
            
            rules = query.order_by(EmailFilterRuleDB.rule_type, EmailFilterRuleDB.pattern).all()
            
            return [
                {
                    'id': rule.id,
                    'rule_type': rule.rule_type,
                    'pattern': rule.pattern,
                    'is_active': rule.is_active,
                    'description': rule.description,
                    'created_at': rule.created_at.isoformat(),
                    'updated_at': rule.updated_at.isoformat()
                }
                for rule in rules
            ]
    
    # ========================================================================
    # SMS Notifications Operations (for Phase 4)
    # ========================================================================
    
    def log_sms_notification(
        self,
        email_message_id: str,
        phone_number: str,
        message_text: str,
        status: str = "sent"
    ) -> int:
        """Log an SMS notification"""
        with self.get_session() as session:
            sms = SMSNotificationDB(
                email_message_id=email_message_id,
                phone_number=phone_number,
                message_text=message_text,
                status=status
            )
            session.add(sms)
            session.commit()
            logger.debug(f"Logged SMS notification for email {email_message_id}")
            return sms.id
    
    def update_sms_response(
        self,
        sms_id: int,
        user_response: str
    ) -> bool:
        """Update SMS notification with user response"""
        with self.get_session() as session:
            sms = session.query(SMSNotificationDB).filter_by(id=sms_id).first()
            
            if not sms:
                return False
            
            sms.user_response = user_response
            sms.response_received_at = datetime.now()
            sms.updated_at = datetime.now()
            session.commit()
            return True
    
    # ========================================================================
    # Audit Log Operations
    # ========================================================================
    
    def log_event(
        self,
        event_type: str,
        event_data: Optional[Dict] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> int:
        """Log an audit event"""
        with self.get_session() as session:
            audit = AuditLogDB(
                event_type=event_type,
                event_data=event_data,
                user_id=user_id,
                ip_address=ip_address
            )
            session.add(audit)
            session.commit()
            return audit.id
