# System Patterns

This file documents recurring patterns and standards used in the project.
It is optional, but recommended to be updated as the project evolves.

2026-01-11 20:05:25 - Initial Memory Bank creation

---

## Coding Patterns

### Python Code Style
- **Framework**: FastAPI for REST APIs
- **Type Hints**: Full type annotations using Python typing module
- **Models**: Pydantic for data validation and serialization
- **Async**: Async/await patterns for I/O operations
- **Error Handling**: HTTP exceptions with appropriate status codes

### Project Structure
```
service-name/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app and routes
│   ├── models.py        # Pydantic models
│   └── client.py        # External service clients
├── tests/
│   ├── __init__.py
│   └── test_*.py        # Test files
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

### Configuration Management
- Environment variables via `.env` files (local development)
- Environment variables passed via Ansible vault (production)
- Sensitive data (passwords, keys) never committed
- `.env.example` provided as template
- Configuration loaded at startup

### API Endpoint Patterns
- RESTful conventions: `/resource/action` or `/resource/{id}`
- Health check at `/health`
- Consistent response formats
- Proper HTTP status codes (200, 201, 400, 404, 500)

## Architectural Patterns

### Microservices Architecture
- Each phase/component as independent service
- Services communicate via HTTP REST APIs
- Each service has own repository structure
- Independent deployment and scaling

### Webhook Pattern
- Incoming webhooks for event-driven architecture
- HMAC signature verification for security
- Idempotent webhook handlers
- Webhook payload validation with Pydantic

### Client Wrapper Pattern
- Dedicated client classes for external services
- Encapsulate authentication and error handling
- Type-safe request/response handling
- Example: `SMSClient` for Android Gateway

### Configuration Pattern
```python
# Environment variables with defaults
ANDROID_GATEWAY_URL = os.getenv("ANDROID_GATEWAY_URL")
YOUR_PHONE_NUMBER = os.getenv("YOUR_PHONE_NUMBER")
SMS_GATEWAY_USERNAME = os.getenv("SMS_GATEWAY_USERNAME")
SMS_GATEWAY_PASSWORD = os.getenv("SMS_GATEWAY_PASSWORD")
```

## Testing Patterns

### Test Structure
- Tests in separate `tests/` directory
- Test files named `test_*.py`
- Use pytest framework
- Mock external dependencies

### Test Coverage Areas
- Endpoint functionality
- Request/response validation
- Error handling
- Authentication/authorization
- Webhook signature verification

## Deployment Patterns

### Ansible Automation
- **Playbook Location**: `/home/jack/workspace/home-server-related/ansible/playbook/email-auto-reply.yml`
- **Deployment Target**: Proxmox LXC container (ID: 118)
- **Infrastructure**: Debian 12 LXC on Proxmox node `jackproxmox`
- **Secrets Management**: Ansible Vault (`../vault/secrets.yml`)

### LXC Container Configuration
- **Container ID**: 118
- **IP Address**: 192.168.1.238
- **Hostname**: email-auto-reply
- **OS Template**: debian-12-standard_12.7-1_amd64.tar.zst
- **Resources**: 512MB RAM, 1 CPU core, 4GB disk
- **Services**: Docker, Filebeat

### Docker Deployment Inside LXC
- Docker installed and managed inside LXC container
- Application runs as Docker container within LXC
- Container name: `sms-gateway`
- Internal port: 8000
- Restart policy: `unless-stopped`
- Environment variables injected at runtime from Ansible vault

### Build and Deploy Process
1. Ansible copies source files to LXC `/tmp/sms-gateway/`
2. Docker image built inside LXC: `docker build -t sms-gateway`
3. Old container removed: `docker rm -f sms-gateway`
4. New container started with environment variables from vault
5. Filebeat configured for log forwarding to Kafka

### Logging Infrastructure
- **Filebeat**: Installed in LXC, monitors Docker container logs
- **Log Path**: `/var/lib/docker/containers/*/*.log`
- **Output**: Kafka cluster (192.168.1.221-223:9092)
- **Topic**: `docker_logs`
- **Service Tag**: `email-auto-reply`
- **Compression**: gzip

### Reverse Proxy Pattern
- Traefik as HTTPS termination point (192.168.1.239)
- Services run on internal ports
- External access via domain names (sms.jackan.xyz)
- Automatic SSL certificate management

### Network Configuration
- Static IPs for critical devices:
  - Android phone (Moto E14): 192.168.1.224:8080
  - Email-auto-reply LXC: 192.168.1.238:8000
  - Traefik reverse proxy: 192.168.1.239
  - Kafka cluster: 192.168.1.221-223:9092
- Internal service communication via local network
- External webhooks via HTTPS domains
- Clear network topology documentation

## Security Patterns

### Authentication
- Basic auth for Android Gateway API
- Credentials stored in Ansible vault (production)
- Credentials in `.env` files (local development)
- HMAC signatures for webhook verification
- Future: OAuth2 for Gmail API

### Data Protection
- Sensitive data in Ansible vault (production)
- Sensitive data in `.env` files (local development, gitignored)
- HTTPS for all external communication
- Webhook signature validation
- No hardcoded credentials in code
- SSH root login enabled for container management

## Logging Patterns

### Application Logging
- Message history stored in-memory (Phase 1)
- Structured log format with timestamps
- Filtering capabilities (by phone number, direction)
- Future: Persistent storage for production

### Infrastructure Logging
- Docker container logs captured by Filebeat
- Logs forwarded to centralized Kafka cluster
- Service identification via `service: email-auto-reply` field
- Real-time log streaming available via `docker logs -f`

## Database Patterns (Phase 2)

### SQLAlchemy ORM Pattern
- Declarative base models for all tables
- Automatic session management with context managers
- Connection pooling (10 connections max)
- No manual commit/rollback - ORM handles transactions
- Type-safe queries with model classes

### Database Manager Pattern
```python
class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, pool_size=10)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    # Methods use context managers for automatic cleanup
    def is_processed(self, message_id: str) -> bool:
        with self.get_session() as session:
            return session.query(Model).filter_by(...).first() is not None
```

### State Management Pattern
- All email state in PostgreSQL (no file-based storage)
- Status field tracks lifecycle: pending → sent/ignored/failed
- Idempotent operations (check before insert)
- Indexed queries for performance
- Audit trail via created_at/updated_at timestamps

## Email Processing Patterns (Phase 2)

### IMAP Polling Pattern
- Background asyncio task runs continuously
- Configurable poll interval (default 120 seconds)
- Fetch only UNSEEN emails
- Parse headers, body (text/HTML), threading info
- Mark as processed in database to avoid reprocessing

### Email Parsing Pattern
```python
# Extract both text and HTML bodies
def _extract_body(email_message):
    body_text = None
    body_html = None
    
    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                body_text = part.get_payload(decode=True)
            elif part.get_content_type() == "text/html":
                body_html = part.get_payload(decode=True)
    
    return body_text, body_html
```

### Filter Rules Pattern
- Database-driven configuration (not environment variables)
- Priority: Blacklist → Whitelist → Default (accept)
- Pattern matching: exact match or domain match (@example.com)
- Case-insensitive matching
- Manageable via REST API without redeployment

## API Endpoint Patterns (Phase 2)

### Email Monitor Endpoints
- `GET /health` - Service health with email counts
- `GET /emails/pending` - Emails awaiting AI reply
- `GET /emails/processed` - All processed emails
- `GET /emails/{message_id}` - Specific email status
- `POST /emails/{message_id}/status` - Update email status
- `GET /filter/config` - Current filter configuration
- `GET /filter/rules` - All filter rules
- `POST /filter/rules` - Add new filter rule
- `DELETE /filter/rules/{id}` - Remove filter rule
- `POST /cleanup?days=30` - Clean up old entries

### Response Format Pattern
```python
# Consistent response structure
{
    "emails": [...],  # or "rules", "status", etc.
    "total": 39
}

# Health check format
{
    "status": "healthy",
    "service": "email-monitor",
    "processed_emails": 39,
    "pending_emails": 39
}
```

## Deployment Patterns (Phase 2)

### Multi-Service LXC Pattern
- Single LXC hosts multiple Docker containers
- Each service on different port (SMS: 8000, Email: 8001)
- Shared infrastructure (Filebeat, Kafka logging)
- Independent restart/rebuild per service
- Ansible playbook deploys all services

### Database Connection Pattern
- Service connects to external PostgreSQL server
- Connection string from environment variables
- Password from Ansible vault
- Connection pooling for efficiency
- Automatic reconnection on failure

### Environment Variable Pattern
```bash
# Email Monitor Configuration
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
EMAIL_ADDRESS=junzhouan@gmail.com
EMAIL_PASSWORD={{ GMAIL_APP_PASSWORD }}  # from vault
POLL_INTERVAL=120

# Database Configuration
DB_HOST=192.168.1.228
DB_PORT=5432
DB_NAME=email_auto_reply
DB_USER=readwrite
DB_PASSWORD={{ ALGO_TRADING_DB_PASSWORD_RW }}  # from vault
```

---

## Update Log
2026-01-11 20:05:25 - Initial system patterns documented based on Phase 1 implementation and Ansible deployment configuration
2026-01-12 13:47:00 - Added Phase 2 patterns: Database (SQLAlchemy), Email Processing (IMAP), API endpoints, Multi-service deployment
