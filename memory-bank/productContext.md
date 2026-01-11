# Product Context

This file provides a high-level overview of the project and the expected product that will be created. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.

2026-01-11 20:01:15 - Initial Memory Bank creation

---

## Project Goal

Build an automated email reply system that monitors Gmail, uses Claude AI to generate contextual reply drafts, and allows approval/editing/ignoring via SMS interface on an Android phone.

## Key Features

### Core Functionality
- **Email Monitoring**: Watch Gmail inbox for new emails requiring responses
- **AI-Powered Replies**: Use Claude API to generate contextual, appropriate reply drafts
- **SMS Control Interface**: Receive draft notifications and control via SMS commands (approve/edit/ignore)
- **Automated Sending**: Send approved replies back through Gmail

### Technical Features
- Webhook-based architecture for real-time processing
- HMAC signature verification for secure webhooks
- Message history and logging
- Docker containerization
- HTTPS endpoints via Traefik reverse proxy

## Overall Architecture

```
Gmail ──webhook──▶ Email Watcher ──▶ Claude API
                                          │
                                          ▼
You ◀──SMS──── Android Phone ◀─── SMS Gateway Service
 │                    │                    ▲
 └─reply "1/2/3"─────▶ (webhook) ─────────┘
                                          │
                                          ▼
                                  Gmail (send reply)
```

### Components

1. **SMS Gateway Service** (Phase 1 - ✅ Complete)
   - FastAPI application
   - Interfaces with Android SMS Gateway app on Moto E14
   - Endpoints: `/sms/send`, `/sms/incoming`, `/sms/history`, `/health`
   - Deployed at: `sms.jackan.xyz`

2. **Email Monitor** (Phase 2 - Pending)
   - Gmail API/IMAP integration
   - Webhook listener for new emails
   - Email parsing and filtering

3. **AI Reply Generator** (Phase 3 - Pending)
   - Claude API integration
   - Context-aware reply generation
   - Draft formatting

4. **Orchestrator** (Phase 4 - Pending)
   - Coordinates all components
   - Manages workflow state
   - Handles user responses via SMS

### Infrastructure

- **Android Device**: Moto E14 (192.168.1.224:8080)
  - SMS Gateway for Android app
  - Static IP configuration
  - Webhook endpoint configured

- **Service Host**: 192.168.1.238
  - email-auto-reply service
  - Port 8765 (internal)

- **Reverse Proxy**: 192.168.1.239
  - Traefik HTTPS gateway
  - Domain: sms.jackan.xyz

### Repository
- GitHub: `git@github.com:JackBeStrong/email-auto-reply.git`
- Branch: main

---

## Update Log
2026-01-11 20:01:15 - Initial product context created with project overview, architecture, and component breakdown
