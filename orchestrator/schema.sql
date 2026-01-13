-- Orchestrator Database Schema
-- This extends the email_auto_reply database with workflow state tracking

-- Create workflow_state table
CREATE TABLE IF NOT EXISTS workflow_state (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    email_subject VARCHAR(500),
    email_from VARCHAR(255),
    email_to VARCHAR(255),
    email_body_preview TEXT,
    
    -- State tracking
    current_state VARCHAR(50) NOT NULL,
    previous_state VARCHAR(50),
    
    -- AI reply
    ai_reply_text TEXT,
    ai_reply_generated_at TIMESTAMP,
    
    -- SMS notification
    sms_message_id VARCHAR(100),
    sms_sent_at TIMESTAMP,
    sms_phone_number VARCHAR(20),
    
    -- User response
    user_command VARCHAR(20),  -- 'approve', 'edit', 'ignore'
    user_edit_instructions TEXT,  -- User's edit guidance (e.g., "reject meeting with health reason")
    user_responded_at TIMESTAMP,
    edit_iteration INTEGER DEFAULT 0,  -- Track how many times user has edited
    
    -- Reply sending
    reply_sent_at TIMESTAMP,
    reply_message_id VARCHAR(255),
    
    -- Error tracking
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    timeout_at TIMESTAMP,  -- When to timeout if no user response
    
    -- Foreign key
    FOREIGN KEY (message_id) REFERENCES processed_emails(message_id) ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_workflow_current_state ON workflow_state(current_state);
CREATE INDEX IF NOT EXISTS idx_workflow_timeout ON workflow_state(timeout_at);
CREATE INDEX IF NOT EXISTS idx_workflow_created_at ON workflow_state(created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_message_id ON workflow_state(message_id);

-- Add new status values to processed_emails if needed
-- Note: This assumes processed_emails.status is a VARCHAR, not an ENUM
-- If it's an ENUM, you'll need to ALTER TYPE instead

-- Create audit log table for workflow transitions
CREATE TABLE IF NOT EXISTS workflow_audit_log (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(255) NOT NULL,
    from_state VARCHAR(50),
    to_state VARCHAR(50) NOT NULL,
    transition_reason TEXT,
    error_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (message_id) REFERENCES processed_emails(message_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_message_id ON workflow_audit_log(message_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON workflow_audit_log(created_at);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_workflow_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at
DROP TRIGGER IF EXISTS trigger_update_workflow_updated_at ON workflow_state;
CREATE TRIGGER trigger_update_workflow_updated_at
    BEFORE UPDATE ON workflow_state
    FOR EACH ROW
    EXECUTE FUNCTION update_workflow_updated_at();

-- Grant permissions to readwrite user
GRANT SELECT, INSERT, UPDATE, DELETE ON workflow_state TO readwrite;
GRANT SELECT, INSERT, UPDATE, DELETE ON workflow_audit_log TO readwrite;
GRANT USAGE, SELECT ON SEQUENCE workflow_state_id_seq TO readwrite;
GRANT USAGE, SELECT ON SEQUENCE workflow_audit_log_id_seq TO readwrite;

-- Grant read-only permissions to readonly user
GRANT SELECT ON workflow_state TO readonly;
GRANT SELECT ON workflow_audit_log TO readonly;
