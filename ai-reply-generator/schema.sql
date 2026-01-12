-- AI Reply Generator Database Schema
-- This schema extends the email_auto_reply database

-- Reply drafts table
CREATE TABLE IF NOT EXISTS reply_drafts (
    id SERIAL PRIMARY KEY,
    draft_id VARCHAR(8) UNIQUE NOT NULL,
    email_message_id VARCHAR(255) NOT NULL,
    full_draft TEXT NOT NULL,
    short_summary TEXT,
    generated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    tokens_used INTEGER NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    user_action VARCHAR(20),
    user_action_at TIMESTAMP,
    final_reply TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_reply_drafts_draft_id ON reply_drafts(draft_id);
CREATE INDEX IF NOT EXISTS idx_reply_drafts_email_message_id ON reply_drafts(email_message_id);
CREATE INDEX IF NOT EXISTS idx_reply_drafts_status ON reply_drafts(status);
CREATE INDEX IF NOT EXISTS idx_reply_drafts_generated_at ON reply_drafts(generated_at DESC);

-- Foreign key constraint (if processed_emails table exists)
-- ALTER TABLE reply_drafts 
--     ADD CONSTRAINT fk_reply_drafts_email 
--     FOREIGN KEY (email_message_id) 
--     REFERENCES processed_emails(message_id) 
--     ON DELETE CASCADE;

-- Comments
COMMENT ON TABLE reply_drafts IS 'Stores AI-generated email reply drafts';
COMMENT ON COLUMN reply_drafts.draft_id IS 'Short unique ID for SMS reference (e.g., A7B2C3D4)';
COMMENT ON COLUMN reply_drafts.email_message_id IS 'Reference to email in processed_emails table';
COMMENT ON COLUMN reply_drafts.full_draft IS 'Complete generated reply text';
COMMENT ON COLUMN reply_drafts.short_summary IS 'Brief summary for SMS (≤150 chars)';
COMMENT ON COLUMN reply_drafts.tokens_used IS 'Total Claude API tokens consumed';
COMMENT ON COLUMN reply_drafts.status IS 'Draft status: pending, approved, edited, sent, ignored';
COMMENT ON COLUMN reply_drafts.user_action IS 'User action: approve, edit, ignore';
COMMENT ON COLUMN reply_drafts.final_reply IS 'Final reply text after user edits';
