-- ============================================================================
-- Email Auto-Reply System - Database Schema
-- Database: email_auto_reply
-- ============================================================================

-- Create database (run as postgres superuser)
-- Note: Using default locale from template0
CREATE DATABASE email_auto_reply
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    TEMPLATE = template0;

-- Connect to the database
\c email_auto_reply

-- ============================================================================
-- Create Users
-- ============================================================================

-- Create readonly user
CREATE USER readonly WITH PASSWORD 'CHANGE_ME_READONLY_PASSWORD';

-- Create readwrite user
CREATE USER readwrite WITH PASSWORD 'CHANGE_ME_READWRITE_PASSWORD';

-- ============================================================================
-- Email Processing Tables
-- ============================================================================

-- Table: processed_emails
-- Tracks all emails that have been processed by the system
CREATE TABLE processed_emails (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    subject TEXT,
    from_address VARCHAR(255) NOT NULL,
    to_addresses TEXT[],
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    reply_draft TEXT,
    error_message TEXT,
    thread_id VARCHAR(255),
    in_reply_to VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for processed_emails
CREATE INDEX idx_processed_emails_message_id ON processed_emails(message_id);
CREATE INDEX idx_processed_emails_status ON processed_emails(status);
CREATE INDEX idx_processed_emails_from_address ON processed_emails(from_address);
CREATE INDEX idx_processed_emails_processed_at ON processed_emails(processed_at DESC);
CREATE INDEX idx_processed_emails_thread_id ON processed_emails(thread_id);
CREATE INDEX idx_processed_emails_created_at ON processed_emails(created_at DESC);

-- Comments
COMMENT ON TABLE processed_emails IS 'Tracks all emails processed by the email monitor';
COMMENT ON COLUMN processed_emails.message_id IS 'Unique email Message-ID header';
COMMENT ON COLUMN processed_emails.status IS 'Status: pending, sent, ignored, filtered, failed';
COMMENT ON COLUMN processed_emails.reply_draft IS 'AI-generated reply draft';
COMMENT ON COLUMN processed_emails.thread_id IS 'Email thread identifier for conversation tracking';

-- ============================================================================
-- Email Filter Configuration Tables
-- ============================================================================

-- Table: email_filter_rules
-- Stores whitelist/blacklist rules for email filtering
CREATE TABLE email_filter_rules (
    id SERIAL PRIMARY KEY,
    rule_type VARCHAR(50) NOT NULL,  -- 'whitelist_sender', 'blacklist_sender', 'whitelist_subject', 'blacklist_subject'
    pattern VARCHAR(500) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_rule UNIQUE (rule_type, pattern)
);

-- Indexes for email_filter_rules
CREATE INDEX idx_filter_rules_type ON email_filter_rules(rule_type);
CREATE INDEX idx_filter_rules_active ON email_filter_rules(is_active);
CREATE INDEX idx_filter_rules_created_at ON email_filter_rules(created_at DESC);

-- Comments
COMMENT ON TABLE email_filter_rules IS 'Email filtering rules (whitelist/blacklist)';
COMMENT ON COLUMN email_filter_rules.rule_type IS 'Type of rule: whitelist_sender, blacklist_sender, whitelist_subject, blacklist_subject';
COMMENT ON COLUMN email_filter_rules.pattern IS 'Email address, domain (@example.com), or subject keyword';

-- ============================================================================
-- SMS Notification Log (for Phase 4 integration)
-- ============================================================================

-- Table: sms_notifications
-- Tracks SMS notifications sent to user
CREATE TABLE sms_notifications (
    id SERIAL PRIMARY KEY,
    email_message_id VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    message_text TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'sent',
    response_received_at TIMESTAMP WITH TIME ZONE,
    user_response TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    FOREIGN KEY (email_message_id) REFERENCES processed_emails(message_id) ON DELETE CASCADE
);

-- Indexes for sms_notifications
CREATE INDEX idx_sms_notifications_email_id ON sms_notifications(email_message_id);
CREATE INDEX idx_sms_notifications_sent_at ON sms_notifications(sent_at DESC);
CREATE INDEX idx_sms_notifications_status ON sms_notifications(status);
CREATE INDEX idx_sms_notifications_created_at ON sms_notifications(created_at DESC);

-- Comments
COMMENT ON TABLE sms_notifications IS 'Log of SMS notifications sent to user';

-- ============================================================================
-- Audit Log Table
-- ============================================================================

-- Table: audit_log
-- Tracks all significant system events
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB,
    user_id VARCHAR(100),
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for audit_log
CREATE INDEX idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_event_data ON audit_log USING GIN (event_data);

-- Comments
COMMENT ON TABLE audit_log IS 'Audit trail of system events';

-- ============================================================================
-- Triggers for updated_at timestamps
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables with updated_at
CREATE TRIGGER update_processed_emails_updated_at
    BEFORE UPDATE ON processed_emails
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_filter_rules_updated_at
    BEFORE UPDATE ON email_filter_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sms_notifications_updated_at
    BEFORE UPDATE ON sms_notifications
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_audit_log_updated_at
    BEFORE UPDATE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Grant Permissions
-- ============================================================================

-- Grant CONNECT privilege
GRANT CONNECT ON DATABASE email_auto_reply TO readonly;
GRANT CONNECT ON DATABASE email_auto_reply TO readwrite;

-- Grant USAGE on schema
GRANT USAGE ON SCHEMA public TO readonly;
GRANT USAGE ON SCHEMA public TO readwrite;

-- ============================================================================
-- Readonly User Permissions
-- ============================================================================

-- SELECT on all tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;

-- SELECT on sequences (for viewing sequence values)
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO readonly;

-- Ensure future tables are also granted
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO readonly;

-- ============================================================================
-- Readwrite User Permissions
-- ============================================================================

-- Full access to tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO readwrite;

-- USAGE on sequences (for SERIAL columns)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO readwrite;

-- Grant DDL permissions (CREATE, ALTER, DROP) on schema
GRANT CREATE ON SCHEMA public TO readwrite;

-- Grant ability to create/modify/drop tables, indexes, views, functions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO readwrite;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO readwrite;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO readwrite;

-- Ensure future objects are also granted full privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON FUNCTIONS TO readwrite;

-- Grant ability to create and manage types
GRANT USAGE ON SCHEMA public TO readwrite;

-- Note: readwrite can now manage schema without superuser access
-- They can: CREATE TABLE, ALTER TABLE, DROP TABLE, CREATE INDEX, CREATE VIEW, etc.

-- ============================================================================
-- Insert Default Filter Rules (examples - customize as needed)
-- ============================================================================

INSERT INTO email_filter_rules (rule_type, pattern, description) VALUES
    ('blacklist_sender', 'noreply@', 'Block all no-reply addresses'),
    ('blacklist_sender', 'no-reply@', 'Block all no-reply addresses (variant)'),
    ('blacklist_subject', 'unsubscribe', 'Block emails with unsubscribe in subject'),
    ('blacklist_subject', 'newsletter', 'Block newsletter emails');

-- ============================================================================
-- Useful Views
-- ============================================================================

-- View: pending_emails
-- Quick view of emails awaiting processing
CREATE VIEW pending_emails AS
SELECT 
    id,
    message_id,
    subject,
    from_address,
    received_at,
    processed_at,
    reply_draft,
    created_at
FROM processed_emails
WHERE status = 'pending'
ORDER BY processed_at DESC;

-- View: recent_activity
-- Recent email processing activity
CREATE VIEW recent_activity AS
SELECT 
    id,
    message_id,
    subject,
    from_address,
    status,
    processed_at,
    created_at,
    CASE 
        WHEN error_message IS NOT NULL THEN 'Error: ' || error_message
        ELSE 'OK'
    END as result
FROM processed_emails
ORDER BY processed_at DESC
LIMIT 100;

-- View: filter_rules_active
-- Currently active filter rules
CREATE VIEW filter_rules_active AS
SELECT 
    id,
    rule_type,
    pattern,
    description,
    created_at
FROM email_filter_rules
WHERE is_active = TRUE
ORDER BY rule_type, pattern;

-- Grant SELECT on views
GRANT SELECT ON pending_emails TO readonly;
GRANT SELECT ON recent_activity TO readonly;
GRANT SELECT ON filter_rules_active TO readonly;

GRANT SELECT ON pending_emails TO readwrite;
GRANT SELECT ON recent_activity TO readwrite;
GRANT SELECT ON filter_rules_active TO readwrite;

-- ============================================================================
-- Completion Message
-- ============================================================================

\echo '============================================================================'
\echo 'Database schema created successfully!'
\echo '============================================================================'
\echo 'Database: email_auto_reply'
\echo 'Users created: readonly, readwrite'
\echo ''
\echo 'IMPORTANT: Change the default passwords!'
\echo '  ALTER USER readonly WITH PASSWORD '\''your_secure_password'\'';'
\echo '  ALTER USER readwrite WITH PASSWORD '\''your_secure_password'\'';'
\echo ''
\echo 'Connection strings:'
\echo '  Readonly:  postgresql://readonly:password@192.168.1.228:5432/email_auto_reply'
\echo '  Readwrite: postgresql://readwrite:password@192.168.1.228:5432/email_auto_reply'
\echo '============================================================================'

-- ============================================================================
-- Migration: Add body_text and body_html columns to processed_emails table
-- Date: 2026-01-12
-- Description: Adds email body storage to support AI reply generation
-- ============================================================================

-- Add body_text column
ALTER TABLE processed_emails
ADD COLUMN IF NOT EXISTS body_text TEXT;

-- Add body_html column
ALTER TABLE processed_emails
ADD COLUMN IF NOT EXISTS body_html TEXT;

-- Add comments
COMMENT ON COLUMN processed_emails.body_text IS 'Plain text version of email body';
COMMENT ON COLUMN processed_emails.body_html IS 'HTML version of email body';

\echo ''
\echo '============================================================================'
\echo 'Migration completed: Added body_text and body_html columns'
\echo '============================================================================'
