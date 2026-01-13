# AI Reply Generator

AI-powered email reply draft generator using Claude API. Part of the email-auto-reply system.

## Overview

This service generates contextual email reply drafts using Anthropic's Claude API. It integrates with the email-monitor service to fetch email context and provides length-aware formatting for SMS notifications.

## Features

- **Claude API Integration**: Uses Claude 3.5 Sonnet for high-quality reply generation
- **Context-Aware**: Incorporates email thread context and sender information
- **Tone Control**: Supports multiple tones (professional, casual, technical, friendly)
- **SMS-Friendly**: Automatically detects if reply fits in SMS (≤300 chars)
- **Smart Summaries**: Generates short summaries for long replies
- **Draft Management**: Stores drafts in PostgreSQL with user action tracking
- **Edit Support**: Allows regeneration with instructions like "make it more casual"

## Architecture

```
PostgreSQL (processed_emails) → AI Reply Generator → Claude API
                                        ↓
                                   PostgreSQL (reply_drafts)
                                        ↓
                                   SMS Gateway (Phase 4)
```

**Note**: The AI Reply Generator queries the shared PostgreSQL database directly instead of calling the Email Monitor HTTP API. This eliminates timeout issues and improves performance.

## API Endpoints

### Generate Reply
```bash
POST /generate-reply
{
  "email_message_id": "msg_123",
  "tone": "professional",
  "max_length": 500,
  "context_instructions": "Keep it brief"
}
```

### Get Draft
```bash
GET /drafts/{draft_id}
```

### Update Draft Action
```bash
PUT /drafts/{draft_id}/action
{
  "action": "approve",  # or "edit", "ignore"
  "edited_text": "..."  # optional, for edit action
}
```

### List Drafts
```bash
GET /drafts?status=pending&limit=100
```

### Health Check
```bash
GET /health
```

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```bash
# Claude API
ANTHROPIC_API_KEY=your_api_key_here

# Database
DATABASE_URL=postgresql://email_auto_reply:password@192.168.1.228:5432/email_auto_reply

# Service Configuration
SERVICE_PORT=8002
LOG_LEVEL=INFO

# Optional: Model Configuration
CLAUDE_MODEL=claude-sonnet-4-5-20250929
CLAUDE_MAX_TOKENS=1024
CLAUDE_TEMPERATURE=0.7

# Optional: Reply Configuration
SMS_FRIENDLY_MAX_LENGTH=300
SUMMARY_MAX_LENGTH=150
```

## Database Schema

The service creates a `reply_drafts` table:

```sql
CREATE TABLE reply_drafts (
    id SERIAL PRIMARY KEY,
    draft_id VARCHAR(8) UNIQUE NOT NULL,
    email_message_id VARCHAR(255) NOT NULL,
    full_draft TEXT NOT NULL,
    short_summary TEXT,
    generated_at TIMESTAMP DEFAULT NOW(),
    tokens_used INTEGER NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    user_action VARCHAR(20),
    user_action_at TIMESTAMP,
    final_reply TEXT,
    sent_at TIMESTAMP
);
```

## Development

### Local Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the service:
```bash
python -m app.main
# or
uvicorn app.main:app --reload --port 8002
```

### Docker Setup

1. Build and run:
```bash
docker-compose up -d
```

2. View logs:
```bash
docker-compose logs -f
```

3. Stop service:
```bash
docker-compose down
```

## SMS Command Format

When integrated with the orchestrator (Phase 4), users can respond via SMS:

### Approve
```
1
1 A7B2C3D4
```

### Edit with Instructions
```
2 make it more casual
2 A7B2C3D4 make it shorter
```

### Ignore
```
3
3 A7B2C3D4
```

## Reply Generation Flow

1. **Fetch Email Context**: Query email details from `processed_emails` table in database
2. **Generate Reply**: Call Claude API with context-aware prompt
3. **Validate**: Check for placeholders, profanity, length constraints
4. **Format**: Determine if SMS-friendly or needs summary
5. **Store**: Save draft in database with unique ID
6. **Return**: Provide draft details for notification

## Tone Types

- **Professional**: Formal, business-appropriate language
- **Casual**: Friendly, conversational tone
- **Technical**: Precise technical language with details
- **Friendly**: Warm, personable, enthusiastic

## Cost Considerations

Claude API pricing (approximate):
- Input: $3 per million tokens
- Output: $15 per million tokens
- Average reply: ~$0.004 per email

The service logs token usage for all API calls.

## Integration

### With Orchestrator
```python
# Orchestrator calls AI Reply Generator to generate drafts
response = await client.post(
    "http://localhost:8002/generate-reply",
    json={"email_message_id": msg_id}
)
```

### With SMS Gateway (Phase 4)
```python
# Orchestrator formats SMS notification
sms_text = reply_formatter.format_for_sms(
    draft_id=draft_id,
    email_from=email_from,
    email_subject=subject,
    reply_text=full_draft,
    is_sms_friendly=is_sms_friendly
)
```

## Testing

Run tests:
```bash
pytest tests/ -v
```

## Deployment

Service runs on:
- **Port**: 8002
- **Host**: LXC 118 @ 192.168.1.238
- **Database**: PostgreSQL @ 192.168.1.228

## Troubleshooting

### Claude API Errors
- Check `ANTHROPIC_API_KEY` is set correctly
- Verify API key has sufficient credits
- Check rate limits

### Database Connection Issues
- Verify `DATABASE_URL` is correct
- Ensure PostgreSQL is accessible
- Check database credentials

### Email Context Not Found
- Verify email exists in `processed_emails` table
- Check database connection
- Ensure Email Monitor has processed the email

## License

Part of the email-auto-reply project.
