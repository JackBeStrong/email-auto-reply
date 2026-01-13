# Phase 4: Orchestrator Design

## Overview
The Orchestrator is the final integration component that coordinates the entire email auto-reply workflow. It connects the Email Monitor, AI Reply Generator, and SMS Gateway to create a seamless user experience.

## Architecture

### Component Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Workflow State Machine                      │  │
│  │  pending → ai_generated → sms_sent → awaiting_user   │  │
│  │              ↓                ↓            ↓          │  │
│  │           failed         failed      approved/edited  │  │
│  │                                         /ignored      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Email Poller │  │ SMS Handler  │  │ Reply Sender │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
    Email Monitor        SMS Gateway          Gmail SMTP
   (port 8001)          (port 8000)
         ↓
   AI Reply Generator
   (port 8002)
```

## Workflow State Machine

### States
1. **pending** - Email fetched by Email Monitor, awaiting orchestrator processing
2. **ai_generating** - Requesting AI reply from AI Reply Generator
3. **ai_generated** - AI reply received, ready to send SMS
4. **sms_sending** - Sending SMS notification to user
5. **sms_sent** - SMS sent, awaiting user response
6. **awaiting_user** - User notified, waiting for command (approve/edit/ignore)
7. **user_approved** - User approved, sending reply
8. **user_edit_requested** - User provided edit instructions, regenerating with AI
9. **user_ignored** - User chose to ignore, no action
10. **reply_sent** - Reply successfully sent via Gmail
11. **failed** - Error occurred at any stage
12. **timeout** - User didn't respond within timeout period

### State Transitions
```
pending → ai_generating → ai_generated → sms_sending → sms_sent → awaiting_user
                ↓              ↓              ↓                          ↓
              failed        failed         failed          ┌─────────────┼─────────────┐
                                                           ↓             ↓             ↓
                                                    user_approved  user_edit_requested  user_ignored
                                                           ↓             ↓
                                                      reply_sent    ai_generating (with edit instructions)
                                                           ↓             ↓
                                                         failed      ai_generated → sms_sending → awaiting_user
                                                                         ↓                            ↑
                                                                       failed                         │
                                                                                                      │
                                                                                    (iterative loop) ─┘
```

## Database Schema Extensions

### New Table: `workflow_state`
```sql
CREATE TABLE workflow_state (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    email_subject VARCHAR(500),
    email_from VARCHAR(255),
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
    FOREIGN KEY (message_id) REFERENCES processed_emails(message_id)
);

CREATE INDEX idx_workflow_state ON workflow_state(current_state);
CREATE INDEX idx_workflow_timeout ON workflow_state(timeout_at);
```

### Update `processed_emails` table
Add new status values:
- `orchestrating` - Being processed by orchestrator
- `sent` - Reply sent successfully
- `ignored` - User chose to ignore
- `timeout` - User didn't respond in time

## SMS Notification Format

### Design Decision: Multi-SMS Format
Given 160-character SMS limit, use structured multi-part messages:

**SMS 1 (Notification):**
```
📧 Email from: John Doe <john@example.com>
Subject: Meeting tomorrow
[1/3]
```

**SMS 2 (Email Preview):**
```
Email: "Hi, can we meet tomorrow at 2pm to discuss the project?"
[2/3]
```

**SMS 3 (Draft Reply + Commands):**
```
Draft: "Hi John, yes 2pm works. See you then!"
Reply: 1=Send 2=Edit 3=Ignore
[3/3]
```

### Alternative: Single Condensed SMS
```
📧 John: "Meeting tomorrow at 2pm?"
Reply: "Yes, 2pm works!"
1=Send 2=Edit 3=Ignore
```

**Decision**: Use condensed format for short emails, multi-part for longer ones.

## SMS Command Parser

### Command Syntax
- **`1`** or **`approve`** or **`send`** → Send the AI-generated reply as-is
- **`2 <instructions>`** or **`edit <instructions>`** → AI regenerates reply with user's guidance
- **`3`** or **`ignore`** or **`skip`** → Don't reply to this email

### Iterative Edit Workflow
When user sends edit instructions, the orchestrator:
1. Extracts the edit instructions (everything after "2 " or "edit ")
2. Calls AI Reply Generator with original email + edit instructions
3. AI generates new draft incorporating the guidance
4. Sends new draft via SMS
5. User can approve (1), edit again (2), or ignore (3)
6. Process repeats until user approves or ignores

### Examples
```
Initial Draft SMS:
"📧 John: Meeting tomorrow at 2pm?
Draft: Yes, 2pm works. See you then!
1=Send 2=Edit 3=Ignore"

User sends: "2 reject meeting with health reason"
→ Action: AI regenerates with instruction "reject meeting with health reason"

New Draft SMS:
"📧 John: Meeting tomorrow at 2pm?
Draft: Thanks for the invite, but I'm not feeling well tomorrow. Can we reschedule?
1=Send 2=Edit 3=Ignore"

User sends: "2 make it more casual"
→ Action: AI regenerates again with "make it more casual"

New Draft SMS:
"📧 John: Meeting tomorrow at 2pm?
Draft: Hey John, not feeling great tomorrow. Rain check?
1=Send 2=Edit 3=Ignore"

User sends: "1"
→ Action: Send the final draft

---

User sends: "3"
→ Action: Mark as ignored, no reply sent
```

## Gmail SMTP Integration

### Decision: Use Gmail SMTP (not Gmail API)
**Rationale:**
- Simpler authentication (app password)
- No OAuth2 token management
- Standard SMTP library in Python
- Sufficient for sending replies
- Easier deployment (no API credentials)

### Implementation
```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_reply(to: str, subject: str, body: str, 
               in_reply_to: str, references: str):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to
    msg['Subject'] = f"Re: {subject}"
    msg['In-Reply-To'] = in_reply_to
    msg['References'] = references
    
    msg.attach(MIMEText(body, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
```

### Email Threading
Maintain proper threading by including:
- `In-Reply-To`: Original email's Message-ID
- `References`: Chain of Message-IDs in thread
- `Subject`: Prefix with "Re: "

## Orchestrator Components

### 1. Email Poller
- Poll Email Monitor `/emails/pending` every 30 seconds
- For each pending email:
  - Create workflow_state entry
  - Transition to `ai_generating`
  - Request AI reply

### 2. AI Reply Requester
- Call AI Reply Generator `/generate-reply`
- Store AI reply in workflow_state
- Transition to `sms_sending`
- Trigger SMS notification

### 3. SMS Notifier
- Format email + AI reply for SMS
- Call SMS Gateway `/sms/send`
- Store SMS message ID
- Transition to `awaiting_user`
- Set timeout (e.g., 24 hours)

### 4. SMS Response Handler
- Webhook endpoint `/orchestrator/sms-response`
- Parse user command (1/2/3)
- Update workflow_state
- Execute action:
  - **Command 1 (Approve)**: Send reply via Gmail
  - **Command 2 (Edit)**: Extract instructions, call AI with edit guidance, send new draft SMS
  - **Command 3 (Ignore)**: Mark as ignored

### 5. Reply Sender
- Send reply via Gmail SMTP
- Update workflow_state to `reply_sent`
- Update processed_emails status to `sent`

### 6. Timeout Monitor
- Background task checks for timeouts every 5 minutes
- For emails in `awaiting_user` past timeout:
  - Transition to `timeout`
  - Send reminder SMS (optional)
  - Or auto-ignore after 48 hours

### 7. Error Handler
- Catch exceptions at each stage
- Log error details
- Update workflow_state to `failed`
- Implement retry logic (max 3 attempts)
- Send error notification SMS

## API Endpoints

### Orchestrator REST API
```
GET  /health                          - Health check
GET  /workflow/status                 - Overall workflow statistics
GET  /workflow/{message_id}           - Get workflow state for email
POST /workflow/{message_id}/retry     - Retry failed workflow
POST /orchestrator/sms-response       - Webhook for SMS responses
GET  /workflow/pending                - List emails awaiting user response
GET  /workflow/failed                 - List failed workflows
POST /workflow/timeout/{message_id}   - Manually timeout an email
```

## Configuration

### Environment Variables
```bash
# Service URLs
EMAIL_MONITOR_URL=http://localhost:8001
AI_REPLY_GENERATOR_URL=http://localhost:8002
SMS_GATEWAY_URL=http://localhost:8000

# Gmail SMTP
GMAIL_SMTP_SERVER=smtp.gmail.com
GMAIL_SMTP_PORT=465
EMAIL_ADDRESS=junzhouan@gmail.com
EMAIL_PASSWORD={{ GMAIL_APP_PASSWORD }}  # from vault

# SMS Configuration
YOUR_PHONE_NUMBER={{ YOUR_PHONE_NUMBER }}  # from vault

# Database
DB_HOST=192.168.1.228
DB_PORT=5432
DB_NAME=email_auto_reply
DB_USER=readwrite
DB_PASSWORD={{ ALGO_TRADING_DB_PASSWORD_RW }}  # from vault

# Workflow Configuration
POLL_INTERVAL=30  # seconds
USER_RESPONSE_TIMEOUT=86400  # 24 hours in seconds
MAX_RETRY_ATTEMPTS=3
SMS_FORMAT=condensed  # or 'multipart'
```

## Error Handling Strategy

### Retry Logic
- **AI Generation Failure**: Retry up to 3 times with exponential backoff
- **SMS Send Failure**: Retry up to 3 times, then mark as failed
- **Gmail SMTP Failure**: Retry up to 3 times, then notify user via SMS

### Failure Notifications
- Send SMS to user: "⚠️ Failed to send reply to [sender]. Check logs."
- Log detailed error to Kafka via Filebeat
- Store error in workflow_state.error_message

### Timeout Handling
- After 24 hours: Send reminder SMS
- After 48 hours: Auto-ignore and notify user

## Monitoring & Observability

### Health Check Response
```json
{
  "status": "healthy",
  "service": "orchestrator",
  "workflows": {
    "pending": 5,
    "awaiting_user": 12,
    "completed_today": 23,
    "failed": 2
  },
  "last_poll": "2026-01-13T02:15:00Z"
}
```

### Metrics to Track
- Emails processed per hour
- Average time from email → SMS notification
- User response rate (approve/edit/ignore)
- Failure rate by stage
- Average user response time

## Testing Strategy

### Unit Tests
- SMS command parser (including edit instruction extraction)
- State machine transitions (including iterative edit loop)
- Email formatting
- Error handling
- Edit iteration tracking

### Integration Tests
- Email Monitor → Orchestrator flow
- Orchestrator → AI Reply Generator flow (initial + edit)
- Orchestrator → SMS Gateway flow
- Orchestrator → Gmail SMTP flow
- End-to-end: Email → AI → SMS → User Response → Reply Sent

### Test Scenarios
1. Happy path: Email → AI → SMS → Approve → Send
2. Single edit path: Email → AI → SMS → Edit → AI (new draft) → SMS → Approve → Send
3. Multiple edit path: Email → AI → SMS → Edit → AI → SMS → Edit → AI → SMS → Approve → Send
4. Ignore path: Email → AI → SMS → Ignore
5. Edit then ignore: Email → AI → SMS → Edit → AI → SMS → Ignore
6. Timeout path: Email → AI → SMS → (no response) → Timeout
7. Failure paths: AI failure, SMS failure, SMTP failure
8. Retry logic: Transient failures with successful retry
9. Edit iteration limit: Prevent infinite edit loops (max 10 iterations)

## Deployment

### Docker Configuration
```yaml
# docker-compose.yml
version: '3.8'
services:
  orchestrator:
    build: .
    container_name: orchestrator
    ports:
      - "8003:8003"
    environment:
      - EMAIL_MONITOR_URL=http://192.168.1.238:8001
      - AI_REPLY_GENERATOR_URL=http://192.168.1.238:8002
      - SMS_GATEWAY_URL=http://192.168.1.238:8000
      - EMAIL_ADDRESS=${EMAIL_ADDRESS}
      - EMAIL_PASSWORD=${EMAIL_PASSWORD}
      - YOUR_PHONE_NUMBER=${YOUR_PHONE_NUMBER}
      - DB_HOST=192.168.1.228
      - DB_PORT=5432
      - DB_NAME=email_auto_reply
      - DB_USER=readwrite
      - DB_PASSWORD=${DB_PASSWORD}
    restart: unless-stopped
```

### Ansible Deployment
- Add orchestrator to existing `email-auto-reply.yml` playbook
- Deploy to LXC 118 alongside other services
- Port 8003 (internal)
- Filebeat log forwarding to Kafka

## Security Considerations

### SMS Webhook Security
- Verify webhook signature from SMS Gateway
- Validate phone number matches YOUR_PHONE_NUMBER
- Rate limiting on webhook endpoint

### Email Security
- Use app-specific password for Gmail
- Store credentials in Ansible vault
- Validate email addresses before sending

### Database Security
- Use parameterized queries (SQLAlchemy ORM)
- Separate read/write users
- Connection pooling with limits

## Future Enhancements

### Phase 5+ Ideas
1. **Web Dashboard**: View pending emails, approve/edit via web UI
2. **Multiple Users**: Support multiple phone numbers/users
3. **Smart Scheduling**: Delay replies to avoid immediate responses
4. **Reply Templates**: User-defined templates for common replies
5. **Learning**: Track which AI replies get edited, improve prompts
6. **Priority Handling**: VIP senders get faster processing
7. **Conversation Context**: Track multi-email conversations
8. **Attachment Support**: Handle email attachments
9. **Rich Formatting**: HTML email replies with formatting
10. **Analytics Dashboard**: Visualize email/reply statistics

## Implementation Plan

### Step 1: Project Structure
```
orchestrator/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── models.py            # Pydantic models
│   ├── database.py          # Database manager
│   ├── state_machine.py     # Workflow state machine
│   ├── email_poller.py      # Poll Email Monitor
│   ├── ai_client.py         # AI Reply Generator client
│   ├── sms_client.py        # SMS Gateway client
│   ├── gmail_client.py      # Gmail SMTP client
│   ├── command_parser.py    # Parse SMS commands
│   └── workflow_manager.py  # Orchestrate workflow
├── tests/
│   ├── __init__.py
│   ├── test_state_machine.py
│   ├── test_command_parser.py
│   └── test_workflow.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── schema.sql               # Database schema
├── .env.example
└── README.md
```

### Step 2: Database Schema
Create `workflow_state` table and update `processed_emails` status values.

### Step 3: Core Components
Implement in order:
1. Database manager
2. State machine
3. SMS command parser
4. Email poller
5. AI client
6. SMS client
7. Gmail client
8. Workflow manager

### Step 4: API Endpoints
Implement REST API and SMS webhook handler.

### Step 5: Background Tasks
Implement polling and timeout monitoring.

### Step 6: Testing
Write comprehensive tests for all components.

### Step 7: Deployment
Deploy to LXC 118 and test end-to-end.

## Success Criteria

Phase 4 is complete when:
- [ ] Orchestrator polls Email Monitor for pending emails
- [ ] Requests AI replies from AI Reply Generator
- [ ] Sends SMS notifications with draft replies
- [ ] Receives and parses SMS commands (1/2/3)
- [ ] Sends approved/edited replies via Gmail SMTP
- [ ] Handles ignore command appropriately
- [ ] Implements timeout logic (24-48 hours)
- [ ] Handles errors with retry logic
- [ ] All tests pass
- [ ] Deployed to LXC 118 on port 8003
- [ ] End-to-end test: Real email → AI reply → SMS → User response → Reply sent
- [ ] Logging to Kafka via Filebeat
- [ ] Health check endpoint operational

## Timeline Estimate

- Design & Planning: ✅ Complete
- Database Schema: 1 hour
- Core Components: 4-6 hours
- API & Webhooks: 2-3 hours
- Testing: 2-3 hours
- Deployment: 1-2 hours
- End-to-End Testing: 1-2 hours

**Total: 11-17 hours** (1-2 days of focused work)
