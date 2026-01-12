# Decision Log

This file records architectural and implementation decisions using a list format.

2026-01-11 20:03:36 - Initial Memory Bank creation

---

## [2026-01-11 20:03:36] SMS Gateway Architecture

### Decision
Use FastAPI with direct HTTP integration to Android SMS Gateway app, deployed as a standalone service behind Traefik reverse proxy.

### Rationale
- **FastAPI**: Modern, async Python framework with automatic OpenAPI documentation
- **Direct Integration**: Android SMS Gateway app provides REST API, eliminating need for third-party SMS services
- **Standalone Service**: Microservice architecture allows independent scaling and deployment
- **Traefik**: Provides HTTPS termination and routing without modifying application code

### Implementation Details
- Service runs on port 8765 internally
- Exposed via sms.jackan.xyz domain through Traefik (192.168.1.239)
- Android device (Moto E14) has static IP 192.168.1.224:8080
- Webhook security via HMAC signature verification
- Message history stored in-memory (suitable for Phase 1)

---

## [2026-01-11 20:03:36] Android SMS Gateway Selection

### Decision
Use SMS Gateway for Android app (sms-gate.app) running on Moto E14 with static IP configuration.

### Rationale
- **Cost**: Free, no per-message charges unlike Twilio/AWS SNS
- **Control**: Full control over SMS infrastructure
- **Privacy**: Messages stay within local network
- **Reliability**: Direct device access, no third-party dependencies
- **Features**: Webhook support, REST API, message history

### Implementation Details
- Moto E14 configured with static IP 192.168.1.224
- SMS Gateway app listening on port 8080
- Basic authentication (username: jack)
- Webhook registered for `sms:received` events pointing to sms.jackan.xyz
- Supports both sending and receiving SMS

---

## [2026-01-11 20:03:36] Webhook Payload Structure

### Decision
Use nested payload structure with `IncomingSMSWebhook` model containing a `payload` field with message details.

### Rationale
- Matches the actual webhook format from SMS Gateway for Android app
- Separates webhook metadata (deviceId, event, webhookId) from message data
- Allows for future webhook event types beyond SMS
- Type-safe with Pydantic models

### Implementation Details
```python
class SMSPayload(BaseModel):
    messageId: str
    message: str
    phoneNumber: str
    simNumber: int
    receivedAt: str

class IncomingSMSWebhook(BaseModel):
    deviceId: str
    event: str
    id: str
    payload: SMSPayload
    webhookId: str
```

---

## [2026-01-11 20:03:36] Phase-Based Development Approach

### Decision
Implement system in 4 distinct phases: SMS Gateway → Email Monitor → AI Reply Generator → Orchestrator.

### Rationale
- **Risk Reduction**: Test each component independently before integration
- **Iterative Development**: Can validate assumptions at each phase
- **Debugging**: Easier to isolate issues in smaller components
- **Flexibility**: Can adjust architecture based on learnings from earlier phases

### Implementation Details
- Phase 1 (SMS Gateway): ✅ Complete and deployed
- Phase 2 (Email Monitor): ✅ Complete and deployed
- Phase 3 (AI Reply Generator): Next focus area
- Phase 4 (Orchestrator): Final integration layer

---

## [2026-01-12 13:43:00] Email Monitor - IMAP Polling Architecture

### Decision
Use IMAP polling with Python's built-in `imaplib` to monitor Gmail inbox, with configurable polling interval.

### Rationale
- **Simplicity**: IMAP is simpler than Gmail API OAuth2 flow for automated deployment
- **Deployment-Friendly**: App-specific password in Ansible vault, no OAuth token management
- **Universal**: Works with any IMAP server, not just Gmail
- **Sufficient Latency**: 120-second polling interval acceptable for personal use
- **No External Dependencies**: Built-in Python library, no additional API setup

### Alternatives Considered
- **Gmail API with Push Notifications**: More complex (Pub/Sub, webhooks), real-time but overkill
- **Gmail API with Polling**: Still requires OAuth2 setup, harder to automate deployment

### Implementation Details
- Poll interval: 120 seconds (configurable via `POLL_INTERVAL` env var)
- Fetches unread emails only (`UNSEEN` flag)
- Parses email headers, body (text/html), threading info
- Marks emails as processed in database to avoid reprocessing
- Runs as background asyncio task in FastAPI

---

## [2026-01-12 13:43:00] PostgreSQL for State Management

### Decision
Use PostgreSQL with SQLAlchemy ORM for persistent state management instead of file-based storage.

### Rationale
- **Persistence**: Data survives container restarts and redeployments
- **Existing Infrastructure**: PostgreSQL server already running (192.168.1.228)
- **Concurrent Access**: Multiple services can access same data (future phases)
- **Query Capabilities**: Complex queries for reporting and analytics
- **Transaction Safety**: ACID compliance for data integrity
- **No Manual Management**: SQLAlchemy handles connections, commits, rollbacks

### Implementation Details
- Database: `email_auto_reply` on existing PostgreSQL server
- Users: `readonly` (queries), `readwrite` (service access)
- Tables: `processed_emails`, `email_filter_rules`, `sms_notifications`, `audit_log`
- ORM: SQLAlchemy 2.0 with declarative models
- Connection pooling: 10 connections max
- Password from Ansible vault: `ALGO_TRADING_DB_PASSWORD_RW`

---

## [2026-01-12 13:43:00] Database-Driven Email Filtering

### Decision
Store whitelist/blacklist filter rules in PostgreSQL database, manageable via REST API.

### Rationale
- **Dynamic Configuration**: Update rules without redeploying service
- **Persistence**: Rules survive restarts
- **API Management**: Add/remove rules via HTTP endpoints
- **Audit Trail**: Track when rules were added/modified
- **Flexibility**: Support multiple rule types (sender, subject, domain)

### Alternatives Considered
- **Environment Variables**: Static, requires redeploy to change
- **Config Files**: Requires container restart to reload

### Implementation Details
- Rule types: `whitelist_sender`, `blacklist_sender`, `whitelist_subject`, `blacklist_subject`
- Pattern matching: Exact match or domain match (e.g., `@spam.com`)
- Priority: Blacklist checked first, then whitelist
- Default rules: Block `noreply@`, `no-reply@`, `newsletter`, `unsubscribe`
- API endpoints: `GET /filter/rules`, `POST /filter/rules`, `DELETE /filter/rules/{id}`

---

## [2026-01-12 13:43:00] Email Status Workflow

### Decision
Track email processing state with status field: `pending` → `sent`/`ignored`/`failed`.

### Rationale
- **Clear State Machine**: Each email has defined lifecycle
- **Idempotency**: Prevent reprocessing same email
- **Debugging**: Track where emails are in the pipeline
- **Reporting**: Query emails by status for analytics

### Status Values
- **`pending`**: Email fetched, passed filters, awaiting AI reply generation (Phase 3)
- **`filtered`**: Email blocked by blacklist rules, no further processing
- **`sent`**: Reply generated and sent (Phase 4)
- **`ignored`**: User chose to ignore via SMS (Phase 4)
- **`failed`**: Error occurred during processing

### Implementation Details
- Status stored in `processed_emails.status` column
- Indexed for fast queries
- Updated via `DatabaseManager.update_status()` method
- Exposed via REST API: `POST /emails/{message_id}/status`

---

## [2026-01-12 13:43:00] Microservice Deployment Pattern

### Decision
Deploy email-monitor as separate Docker container alongside SMS gateway in same LXC.

### Rationale
- **Independent Scaling**: Each service can be restarted independently
- **Resource Isolation**: Separate containers for better resource management
- **Port Separation**: SMS Gateway (8000), Email Monitor (8001)
- **Shared Infrastructure**: Both use same LXC, Filebeat, Kafka logging
- **Simplified Deployment**: Single Ansible playbook deploys both services

### Implementation Details
- LXC Container: 118 @ 192.168.1.238
- Resources: 1024MB RAM, 2 CPU cores, 8GB disk (shared)
- Containers: `sms-gateway` (port 8000), `email-monitor` (port 8001)
- Logging: Both forward logs to Kafka via Filebeat
- Deployment: Ansible playbook builds and runs both containers

---

## Update Log
2026-01-11 20:03:36 - Initial decision log created with Phase 1 architectural decisions
2026-01-12 13:43:00 - Added Phase 2 (Email Monitor) architectural decisions
