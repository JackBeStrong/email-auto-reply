# SMS Gateway Service

Phase 1 of the Email Auto-Reply system. A FastAPI service that provides 2-way SMS communication via an Android phone running an SMS gateway app.

## Architecture

```
Your Service (this) <---> Android Phone (SMS Gateway App) <---> SMS Network
     :8000                     :8080
```

## Quick Start

### 1. Set Up Android Phone

1. Install an SMS gateway app on your Android phone:
   - [SMS Gateway by CubeSystem](https://play.google.com/store/apps/details?id=eu.cubesystems.smsgateway) (recommended)
   - Or similar app that supports REST API + webhooks

2. Configure the app:
   - Enable REST API server (usually runs on port 8080)
   - Note your phone's local IP address (e.g., `192.168.1.100`)
   - Configure webhook URL to point to your service: `http://YOUR_SERVER_IP:8000/sms/incoming`

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Run with Docker

```bash
docker compose up --build
```

Or run locally:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API Endpoints

### Send SMS
```bash
POST /sms/send
{
  "to": "+14155551234",
  "message": "Hello from the gateway!"
}
```

### Receive SMS (Webhook)
```bash
POST /sms/incoming
{
  "from": "+14155551234",
  "message": "Reply from user"
}
```

### View History
```bash
GET /sms/history
GET /sms/history?direction=incoming
GET /sms/history?phone_number=%2B14155551234
```

### Health Check
```bash
GET /health
```

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app tests/
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Next Steps

This service will integrate with:
- **Phase 2**: Email Monitor (Gmail watcher)
- **Phase 3**: AI Reply Generator (Claude API)
- **Phase 4**: Orchestrator (ties everything together)
