# Email Monitor Service

Phase 2 of the Email Auto-Reply system. A FastAPI service that monitors Gmail inbox via IMAP, filters emails based on configurable rules, and stores state in PostgreSQL.

## Architecture

```
Gmail (IMAP) <---> Email Monitor <---> PostgreSQL
                        |
                        v
                   (Phase 3: AI Reply Generator)
```

## Features

- **IMAP Polling**: Monitors Gmail inbox for new unread emails
- **Configurable Filtering**: Whitelist/blacklist rules for senders and subjects
- **PostgreSQL Storage**: Persistent state management and configuration
- **RESTful API**: Manage emails and filter rules via HTTP endpoints
- **Docker Support**: Containerized deployment

## Prerequisites

1. **Gmail Account** with IMAP enabled
   - Enable IMAP in Gmail settings
   - Generate an [App-Specific Password](https://support.google.com/accounts/answer/185833)

2. **PostgreSQL Database** (v15+)
   - Database: `email_auto_reply`
   - Users: `readonly`, `readwrite`
   - See [`schema.sql`](schema.sql) for setup

## Quick Start

### 1. Set Up PostgreSQL Database

```bash
# Connect to PostgreSQL server
psql -h 192.168.1.228 -U postgres

# Run the schema script
\i schema.sql

# Set passwords (replace with secure passwords)
ALTER USER readonly WITH PASSWORD 'your_readonly_password';
ALTER USER readwrite WITH PASSWORD 'your_readwrite_password';
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

Required environment variables:
- `EMAIL_ADDRESS`: Your Gmail address
- `EMAIL_PASSWORD`: Gmail app-specific password
- `DB_PASSWORD`: PostgreSQL readwrite user password

### 3. Run with Docker

```bash
docker compose up --build
```

Or run locally:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Email Management

**Get pending emails:**
```bash
GET /emails/pending
```

**Get all processed emails:**
```bash
GET /emails/processed?limit=100
```

**Get specific email status:**
```bash
GET /emails/{message_id}
```

**Update email status:**
```bash
POST /emails/{message_id}/status
{
  "status": "sent",
  "reply_draft": "Email reply text",
  "error_message": null
}
```

### Filter Management

**Get current filter configuration:**
```bash
GET /filter/config
```

**Get all filter rules:**
```bash
GET /filter/rules?include_inactive=false
```

**Add filter rule:**
```bash
POST /filter/rules
{
  "rule_type": "blacklist_sender",
  "pattern": "noreply@example.com",
  "description": "Block no-reply emails"
}
```

Rule types:
- `whitelist_sender`: Email address or domain (e.g., `@company.com`)
- `blacklist_sender`: Email address or domain to block
- `whitelist_subject`: Subject keyword to always process
- `blacklist_subject`: Subject keyword to always ignore

**Remove filter rule:**
```bash
DELETE /filter/rules/{rule_id}
```

### Maintenance

**Cleanup old entries:**
```bash
POST /cleanup?days=30
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAP_SERVER` | `imap.gmail.com` | IMAP server address |
| `IMAP_PORT` | `993` | IMAP server port |
| `EMAIL_ADDRESS` | - | Gmail address (required) |
| `EMAIL_PASSWORD` | - | App-specific password (required) |
| `POLL_INTERVAL` | `120` | Polling interval in seconds |
| `DB_HOST` | `192.168.1.228` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `email_auto_reply` | Database name |
| `DB_USER` | `readwrite` | Database user |
| `DB_PASSWORD` | - | Database password (required) |

### Filter Rules

Filter rules are stored in the database and can be managed via API or directly in PostgreSQL:

```sql
-- Add a blacklist rule
INSERT INTO email_filter_rules (rule_type, pattern, description)
VALUES ('blacklist_sender', 'spam@example.com', 'Block spam sender');

-- View active rules
SELECT * FROM filter_rules_active;

-- Deactivate a rule
UPDATE email_filter_rules SET is_active = FALSE WHERE id = 1;
```

## Database Schema

See [`schema.sql`](schema.sql) for complete schema. Key tables:

- **processed_emails**: Tracks all processed emails and their status
- **email_filter_rules**: Whitelist/blacklist configuration
- **sms_notifications**: SMS notification log (Phase 4)
- **audit_log**: System event audit trail

## Development

### Running Tests

```bash
pytest tests/
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
uvicorn app.main:app --reload --port 8001
```

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## Deployment

The service is designed to be deployed via Ansible to a Proxmox LXC container. See the main project's Ansible playbook for deployment configuration.

### Port Configuration

- **Internal**: 8001
- **External**: Configured via Traefik reverse proxy

## Monitoring

### Logs

```bash
# Docker logs
docker compose logs -f email-monitor

# Check health
curl http://localhost:8001/health
```

### Database Queries

```sql
-- Email processing statistics
SELECT status, COUNT(*) as count, MAX(processed_at) as last_processed
FROM processed_emails
GROUP BY status;

-- Recent activity
SELECT * FROM recent_activity LIMIT 20;

-- Pending emails
SELECT * FROM pending_emails;
```

## Troubleshooting

### IMAP Connection Issues

1. Verify IMAP is enabled in Gmail settings
2. Check app-specific password is correct
3. Ensure firewall allows outbound port 993

### Database Connection Issues

1. Verify PostgreSQL is running: `pg_isready -h 192.168.1.228`
2. Check credentials in `.env`
3. Verify network connectivity to database server

### No Emails Being Processed

1. Check filter rules: `GET /filter/rules`
2. Verify emails aren't already processed: `GET /emails/processed`
3. Check logs for errors: `docker compose logs email-monitor`

## Next Steps

This service integrates with:
- **Phase 3**: AI Reply Generator (Claude API) - Coming next
- **Phase 4**: Orchestrator (ties everything together with SMS)

## License

Part of the Email Auto-Reply system.
