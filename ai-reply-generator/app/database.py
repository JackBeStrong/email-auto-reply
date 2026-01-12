"""
Database configuration and manager for AI Reply Generator
"""
import os
import logging
import secrets
import string
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)

Base = declarative_base()


# ============================================================================
# SQLAlchemy Models
# ============================================================================

class ReplyDraftDB(Base):
    """SQLAlchemy model for reply_drafts table"""
    __tablename__ = "reply_drafts"
    
    id = Column(Integer, primary_key=True, index=True)
    draft_id = Column(String(8), unique=True, nullable=False, index=True)
    email_message_id = Column(String(255), nullable=False, index=True)
    full_draft = Column(Text, nullable=False)
    short_summary = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tokens_used = Column(Integer, nullable=False)
    model_version = Column(String(50), nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    user_action = Column(String(20), nullable=True)
    user_action_at = Column(DateTime, nullable=True)
    final_reply = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)


# ============================================================================
# Database Manager
# ============================================================================

class DatabaseManager:
    """Manages database operations for reply drafts"""
    
    def __init__(self, database_url: str):
        """
        Initialize database manager
        
        Args:
            database_url: PostgreSQL connection string
        """
        self.engine = create_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        logger.info(f"Database engine created: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def init_tables(self):
        """Initialize database tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def close(self):
        """Close database engine"""
        self.engine.dispose()
        logger.info("Database engine disposed")
    
    def check_connection(self) -> bool:
        """Check if database connection is working"""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    # ========================================================================
    # Reply Draft Operations
    # ========================================================================
    
    def generate_draft_id(self) -> str:
        """
        Generate a unique short draft ID (e.g., 'A7B2')
        
        Returns:
            8-character alphanumeric ID
        """
        chars = string.ascii_uppercase + string.digits
        while True:
            draft_id = ''.join(secrets.choice(chars) for _ in range(8))
            # Check if ID already exists
            with self.get_session() as session:
                existing = session.query(ReplyDraftDB).filter_by(draft_id=draft_id).first()
                if not existing:
                    return draft_id
    
    def create_draft(
        self,
        email_message_id: str,
        full_draft: str,
        short_summary: Optional[str],
        tokens_used: int,
        model_version: str
    ) -> str:
        """
        Create a new reply draft
        
        Returns:
            The generated draft_id
        """
        draft_id = self.generate_draft_id()
        
        with self.get_session() as session:
            draft = ReplyDraftDB(
                draft_id=draft_id,
                email_message_id=email_message_id,
                full_draft=full_draft,
                short_summary=short_summary,
                tokens_used=tokens_used,
                model_version=model_version,
                status="pending"
            )
            session.add(draft)
            session.commit()
            logger.info(f"Created draft {draft_id} for email {email_message_id}")
            return draft_id
    
    def get_draft(self, draft_id: str) -> Optional[Dict]:
        """Get a draft by ID"""
        with self.get_session() as session:
            draft = session.query(ReplyDraftDB).filter_by(draft_id=draft_id).first()
            
            if not draft:
                return None
            
            return {
                'id': draft.id,
                'draft_id': draft.draft_id,
                'email_message_id': draft.email_message_id,
                'full_draft': draft.full_draft,
                'short_summary': draft.short_summary,
                'generated_at': draft.generated_at,
                'tokens_used': draft.tokens_used,
                'model_version': draft.model_version,
                'status': draft.status,
                'user_action': draft.user_action,
                'user_action_at': draft.user_action_at,
                'final_reply': draft.final_reply,
                'sent_at': draft.sent_at
            }
    
    def get_draft_by_email(self, email_message_id: str) -> Optional[Dict]:
        """Get the most recent draft for an email"""
        with self.get_session() as session:
            draft = session.query(ReplyDraftDB).filter_by(
                email_message_id=email_message_id
            ).order_by(ReplyDraftDB.generated_at.desc()).first()
            
            if not draft:
                return None
            
            return {
                'id': draft.id,
                'draft_id': draft.draft_id,
                'email_message_id': draft.email_message_id,
                'full_draft': draft.full_draft,
                'short_summary': draft.short_summary,
                'generated_at': draft.generated_at,
                'tokens_used': draft.tokens_used,
                'model_version': draft.model_version,
                'status': draft.status,
                'user_action': draft.user_action,
                'user_action_at': draft.user_action_at,
                'final_reply': draft.final_reply,
                'sent_at': draft.sent_at
            }
    
    def update_draft_action(
        self,
        draft_id: str,
        action: str,
        final_reply: Optional[str] = None
    ) -> bool:
        """
        Update draft with user action
        
        Args:
            draft_id: Draft ID
            action: User action (approve, edit, ignore)
            final_reply: Final reply text (for edit action)
            
        Returns:
            True if successful, False if draft not found
        """
        with self.get_session() as session:
            draft = session.query(ReplyDraftDB).filter_by(draft_id=draft_id).first()
            
            if not draft:
                logger.warning(f"Draft {draft_id} not found")
                return False
            
            draft.user_action = action
            draft.user_action_at = datetime.utcnow()
            
            if action == "approve":
                draft.status = "approved"
                draft.final_reply = draft.full_draft
            elif action == "edit":
                draft.status = "edited"
                draft.final_reply = final_reply
            elif action == "ignore":
                draft.status = "ignored"
            
            session.commit()
            logger.info(f"Updated draft {draft_id} with action: {action}")
            return True
    
    def mark_draft_sent(self, draft_id: str) -> bool:
        """Mark a draft as sent"""
        with self.get_session() as session:
            draft = session.query(ReplyDraftDB).filter_by(draft_id=draft_id).first()
            
            if not draft:
                return False
            
            draft.status = "sent"
            draft.sent_at = datetime.utcnow()
            session.commit()
            logger.info(f"Marked draft {draft_id} as sent")
            return True
    
    def get_pending_drafts(self, limit: int = 100) -> List[Dict]:
        """Get all pending drafts"""
        with self.get_session() as session:
            drafts = session.query(ReplyDraftDB).filter_by(
                status="pending"
            ).order_by(ReplyDraftDB.generated_at.desc()).limit(limit).all()
            
            return [
                {
                    'id': draft.id,
                    'draft_id': draft.draft_id,
                    'email_message_id': draft.email_message_id,
                    'full_draft': draft.full_draft,
                    'short_summary': draft.short_summary,
                    'generated_at': draft.generated_at,
                    'tokens_used': draft.tokens_used,
                    'model_version': draft.model_version,
                    'status': draft.status
                }
                for draft in drafts
            ]
    
    def get_all_drafts(self, limit: int = 100) -> List[Dict]:
        """Get all drafts"""
        with self.get_session() as session:
            drafts = session.query(ReplyDraftDB).order_by(
                ReplyDraftDB.generated_at.desc()
            ).limit(limit).all()
            
            return [
                {
                    'id': draft.id,
                    'draft_id': draft.draft_id,
                    'email_message_id': draft.email_message_id,
                    'full_draft': draft.full_draft[:100] + '...' if len(draft.full_draft) > 100 else draft.full_draft,
                    'short_summary': draft.short_summary,
                    'generated_at': draft.generated_at,
                    'status': draft.status,
                    'user_action': draft.user_action
                }
                for draft in drafts
            ]

