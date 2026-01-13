"""
Database manager for Orchestrator service

Handles workflow state persistence and audit logging.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.models import WorkflowStateCreate, WorkflowStateUpdate

Base = declarative_base()


class WorkflowStateDB(Base):
    """SQLAlchemy model for workflow_state table"""
    __tablename__ = 'workflow_state'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(String(255), unique=True, nullable=False)
    email_subject = Column(String(500))
    email_from = Column(String(255))
    email_to = Column(String(255))
    email_body_preview = Column(Text)
    
    current_state = Column(String(50), nullable=False)
    previous_state = Column(String(50))
    
    ai_reply_text = Column(Text)
    ai_reply_generated_at = Column(DateTime)
    
    sms_message_id = Column(String(100))
    sms_sent_at = Column(DateTime)
    sms_phone_number = Column(String(20))
    
    user_command = Column(String(20))
    user_edit_instructions = Column(Text)
    user_responded_at = Column(DateTime)
    edit_iteration = Column(Integer, default=0)
    
    reply_sent_at = Column(DateTime)
    reply_message_id = Column(String(255))
    
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    timeout_at = Column(DateTime)


class WorkflowAuditLogDB(Base):
    """SQLAlchemy model for workflow_audit_log table"""
    __tablename__ = 'workflow_audit_log'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(String(255), nullable=False)
    from_state = Column(String(50))
    to_state = Column(String(50), nullable=False)
    transition_reason = Column(Text)
    error_details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DatabaseManager:
    """Manage database operations for workflow state"""
    
    def __init__(self, database_url: str):
        """
        Initialize database manager.
        
        Args:
            database_url: PostgreSQL connection string
        """
        self.engine = create_engine(database_url, pool_size=10, max_overflow=20)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def create_workflow(self, workflow: WorkflowStateCreate) -> WorkflowStateDB:
        """
        Create a new workflow state entry.
        
        Args:
            workflow: Workflow state creation data
            
        Returns:
            Created workflow state
        """
        with self.get_session() as session:
            db_workflow = WorkflowStateDB(**workflow.model_dump())
            session.add(db_workflow)
            session.commit()
            session.refresh(db_workflow)
            
            # Log the creation
            self._log_transition(
                session,
                workflow.message_id,
                None,
                workflow.current_state,
                "Workflow created"
            )
            session.commit()
            
            return db_workflow
    
    def get_workflow(self, message_id: str) -> Optional[WorkflowStateDB]:
        """
        Get workflow state by message ID.
        
        Args:
            message_id: Email message ID
            
        Returns:
            Workflow state or None if not found
        """
        with self.get_session() as session:
            return session.query(WorkflowStateDB).filter_by(message_id=message_id).first()
    
    def update_workflow(self, message_id: str, update: WorkflowStateUpdate) -> Optional[WorkflowStateDB]:
        """
        Update workflow state.
        
        Args:
            message_id: Email message ID
            update: Fields to update
            
        Returns:
            Updated workflow state or None if not found
        """
        with self.get_session() as session:
            workflow = session.query(WorkflowStateDB).filter_by(message_id=message_id).first()
            if not workflow:
                return None
            
            # Track state transition
            old_state = workflow.current_state
            
            # Update fields
            update_data = update.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(workflow, key, value)
            
            session.commit()
            session.refresh(workflow)
            
            # Log state transition if state changed
            if 'current_state' in update_data and update_data['current_state'] != old_state:
                self._log_transition(
                    session,
                    message_id,
                    old_state,
                    update_data['current_state'],
                    f"State transition"
                )
                session.commit()
            
            return workflow
    
    def get_workflows_by_state(self, state: str, limit: int = 100) -> List[WorkflowStateDB]:
        """
        Get workflows in a specific state.
        
        Args:
            state: Current state to filter by
            limit: Maximum number of results
            
        Returns:
            List of workflows
        """
        with self.get_session() as session:
            return session.query(WorkflowStateDB)\
                .filter_by(current_state=state)\
                .order_by(WorkflowStateDB.created_at.desc())\
                .limit(limit)\
                .all()
    
    def get_timed_out_workflows(self) -> List[WorkflowStateDB]:
        """
        Get workflows that have timed out.
        
        Returns:
            List of timed out workflows
        """
        with self.get_session() as session:
            now = datetime.utcnow()
            return session.query(WorkflowStateDB)\
                .filter(
                    WorkflowStateDB.current_state == 'awaiting_user',
                    WorkflowStateDB.timeout_at <= now
                )\
                .all()
    
    def get_workflow_statistics(self) -> dict:
        """
        Get workflow statistics.
        
        Returns:
            Dictionary with workflow counts by state
        """
        with self.get_session() as session:
            total = session.query(WorkflowStateDB).count()
            
            # Count by state
            states = {}
            for state in ['pending', 'ai_generating', 'awaiting_user', 'failed', 'timeout']:
                count = session.query(WorkflowStateDB).filter_by(current_state=state).count()
                states[state] = count
            
            # Count completed today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            completed_today = session.query(WorkflowStateDB)\
                .filter(
                    WorkflowStateDB.current_state == 'reply_sent',
                    WorkflowStateDB.reply_sent_at >= today_start
                )\
                .count()
            
            return {
                'total_workflows': total,
                'pending': states.get('pending', 0),
                'ai_generating': states.get('ai_generating', 0),
                'awaiting_user': states.get('awaiting_user', 0),
                'completed_today': completed_today,
                'failed': states.get('failed', 0),
                'timeout': states.get('timeout', 0),
            }
    
    def workflow_exists(self, message_id: str) -> bool:
        """
        Check if a workflow exists for a message ID.
        
        Args:
            message_id: Email message ID
            
        Returns:
            True if workflow exists, False otherwise
        """
        with self.get_session() as session:
            return session.query(WorkflowStateDB).filter_by(message_id=message_id).first() is not None
    
    def _log_transition(self, session: Session, message_id: str, from_state: Optional[str], 
                       to_state: str, reason: str, error: Optional[str] = None):
        """
        Log a workflow state transition.
        
        Args:
            session: Database session
            message_id: Email message ID
            from_state: Previous state
            to_state: New state
            reason: Reason for transition
            error: Error details if applicable
        """
        log_entry = WorkflowAuditLogDB(
            message_id=message_id,
            from_state=from_state,
            to_state=to_state,
            transition_reason=reason,
            error_details=error
        )
        session.add(log_entry)
    
    def get_audit_log(self, message_id: str) -> List[WorkflowAuditLogDB]:
        """
        Get audit log for a workflow.
        
        Args:
            message_id: Email message ID
            
        Returns:
            List of audit log entries
        """
        with self.get_session() as session:
            return session.query(WorkflowAuditLogDB)\
                .filter_by(message_id=message_id)\
                .order_by(WorkflowAuditLogDB.created_at.asc())\
                .all()


def get_database_manager() -> DatabaseManager:
    """
    Get database manager instance.
    
    Returns:
        DatabaseManager instance
    """
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'email_auto_reply')
    db_user = os.getenv('DB_USER', 'readwrite')
    db_password = os.getenv('DB_PASSWORD', '')
    
    database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return DatabaseManager(database_url)
