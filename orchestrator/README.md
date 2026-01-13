# Orchestrator Service

The Orchestrator is the final integration component (Phase 4) of the Email Auto-Reply system. It coordinates the entire workflow by connecting the Email Monitor, AI Reply Generator, and SMS Gateway services.

## Features

- **Email Polling**: Polls Email Monitor every 2 minutes for pending emails
- **AI Reply Generation**: Requests AI-generated replies from AI Reply Generator
- **SMS Notifications**: Sends draft replies to user via SMS
- **Iterative Editing**: Supports user edit instructions (e.g., "2 make it more casual")
- **User Commands**: Approve (1), Edit (2), or Ignore (3) emails via SMS
- **Gmail Integration**: Sends approved replies via Gmail SMTP
- **Error Handling**: Automatic retry logic with exponential backoff
- **Timeout Management**: Handles user response timeouts
- **Workflow Tracking**: Complete audit trail in PostgreSQL

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Workflow State Machine                      │  │
│  │  pending → ai_generated → awaiting_user → sent       │  │
│  │              ↓                ↓            ↓          │  │
│  │           failed         failed      approved/edited  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Email Poller │  │ SMS Handler  │  │ Reply Sender │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
   PostgreSQL DB        SMS Gateway          Gmail SMTP
  (Direct Query)       (port 8000)
         ↓
   AI Reply Generator
   (port 8002)
```

**Note**: The orchestrator queries the shared PostgreSQL database directly instead of calling the Email Monitor HTTP API. This eliminates timeout issues and improves performance.

## Workflow States

1. **pending** - Email fetched, awaiting AI reply
2. **ai_generating** - Requesting AI reply
3. **ai_generated** - AI reply received
4. **sms_sending** - Sending SMS notification
5. **awaiting_user** - Waiting for user response
6. **user_approved** - User approved, sending reply
7. **user_edit_requested** - User requested edit, regenerating
8. **user_ignored** - User chose to ignore
9. **reply_sent** - Reply sent successfully
10. **failed** - Error occurred
11. **timeout** - User didn't respond in time

## User Commands

### SMS Command Format

- **`1`** or **`send`** or **`approve`** → Send the AI-generated reply as-is
- **`2 <instructions>`** → AI regenerates reply with your guidance
- **`3`** or **`ignore`** → Don't reply to this email

### Iterative Edit Workflow

```
Initial Draft SMS:
"📧 John: Meeting tomorrow at 2pm?
Draft: Yes, 2pm works. See you then!
1=Send 2=Edit 3=Ignore"

User: "2 reject meeting with health reason"
→ AI regenerates with instruction

New Draft SMS:
"📧 John: Meeting tomorrow at 2pm?
Draft: Thanks for the invite, but I'm not feeling well tomorrow. Can we reschedule?
1=Send 2=Edit 3=Ignore"

User: "1"
→ Reply sent!
```

## API Endpoints

### Health & Status
- `GET /health` - Health check with workflow statistics
- `GET /workflow/status` - Overall workflow statistics

### Workflow Management
- `GET /workflow/{message_id}` - Get workflow state for email
- `GET /workflow/pending` - List emails awaiting user response
- `GET /workflow/failed` - List failed workflows
- `POST /workflow/{message_id}/retry` - Retry failed workflow
- `POST /workflow/timeout/{message_id}` - Manually timeout workflow

### Webhooks
- `POST /orchestrator/sms-response` - Webhook for incoming SMS responses

## Configuration

### Environment Variables

```bash
# Service URLs
AI_REPLY_GENERATOR_URL=http://192.168.1.238:8002
SMS_GATEWAY_URL=http://192.168.1.238:8000

# Gmail SMTP
GMAIL_SMTP_SERVER=smtp.gmail.com
GMAIL_SMTP_PORT=465
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-specific-password

# SMS Configuration
YOUR_PHONE_NUMBER=+1234567890

# Database
DB_HOST=192.168.1.228
DB_PORT=5432
DB_NAME=email_auto_reply
DB_USER=readwrite
DB_PASSWORD=your-password

# Workflow Configuration
POLL_INTERVAL=120                    # Poll every 2 minutes
USER_RESPONSE_TIMEOUT=86400          # 24 hours
MAX_RETRY_ATTEMPTS=3
MAX_EDIT_ITERATIONS=10
SMS_FORMAT=condensed
```

## Database Schema

The orchestrator extends the `email_auto_reply` database with:

### `workflow_state` Table
Tracks the state of each email workflow:
- Email details (subject, from, body preview)
- Current and previous states
- AI reply text and generation time
- SMS notification details
- User response and edit instructions
- Reply sending details
- Error tracking and retry count
- Timestamps and timeout

### `workflow_audit_log` Table
Audit trail of all state transitions:
- State transitions (from → to)
- Transition reasons
- Error details
- Timestamps

## Setup

### 1. Database Setup

```bash
# Connect to PostgreSQL
psql -h 192.168.1.228 -U postgres -d email_auto_reply

# Run schema
\i schema.sql
```

### 2. Local Development

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env

# Install dependencies
pip install -r requirements.txt

# Run the service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003
```

### 3. Docker Deployment

```bash
# Build image
docker build -t orchestrator .

# Run container
docker-compose up -d

# View logs
docker logs -f orchestrator
```

## Testing

```bash
# Run tests
pytest

# Run specific test
pytest tests/test_command_parser.py

# Run with coverage
pytest --cov=app tests/
```

## Deployment

The orchestrator is deployed to LXC 118 (192.168.1.238) alongside the other services:

- **SMS Gateway**: port 8000
- **Email Monitor**: port 8001
- **AI Reply Generator**: port 8002
- **Orchestrator**: port 8003

All services share the same PostgreSQL database and log to Kafka via Filebeat.

## Monitoring

### Health Check
```bash
curl http://192.168.1.238:8003/health
```

### Workflow Statistics
```bash
curl http://192.168.1.238:8003/workflow/status
```

### Pending Workflows
```bash
curl http://192.168.1.238:8003/workflow/pending
```

### Failed Workflows
```bash
curl http://192.168.1.238:8003/workflow/failed
```

## Troubleshooting

### No SMS notifications received
1. Check SMS Gateway is running: `curl http://192.168.1.238:8000/health`
2. Check orchestrator logs: `docker logs orchestrator`
3. Verify YOUR_PHONE_NUMBER is correct in .env

### AI replies not generating
1. Check AI Reply Generator is running: `curl http://192.168.1.238:8002/health`
2. Check Claude API key is valid
3. Check orchestrator logs for errors

### Emails not being processed
1. Check Email Monitor is running: `curl http://192.168.1.238:8001/health`
2. Check database for pending emails: Query `processed_emails` table with status='pending'
3. Check orchestrator poll interval (default 2 minutes)
4. Check orchestrator logs for database connection issues

### Gmail sending fails
1. Verify EMAIL_ADDRESS and EMAIL_PASSWORD are correct
2. Ensure you're using an app-specific password (not your regular Gmail password)
3. Check Gmail SMTP settings (smtp.gmail.com:465)

### Database connection issues
1. Verify database credentials in .env
2. Check PostgreSQL is accessible: `psql -h 192.168.1.228 -U readwrite -d email_auto_reply`
3. Ensure workflow_state table exists: `\dt workflow_state`

## Security

- **SMS Verification**: Only processes SMS from YOUR_PHONE_NUMBER
- **Database**: Uses separate read/write users with limited permissions
- **Credentials**: All sensitive data in environment variables (Ansible vault in production)
- **Non-root User**: Docker container runs as non-root user
- **HTTPS**: External access via Traefik reverse proxy (future)

## Future Enhancements

- Web dashboard for workflow management
- Multiple user support
- Smart reply scheduling
- Reply templates
- Learning from user edits
- Priority handling for VIP senders
- Attachment support
- HTML email formatting
- Analytics dashboard

## License

Part of the Email Auto-Reply system.
