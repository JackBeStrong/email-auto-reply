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
- Phase 2 (Email Monitor): Next focus area
- Phase 3 (AI Reply Generator): Depends on Phase 2 completion
- Phase 4 (Orchestrator): Final integration layer

---

## Update Log
2026-01-11 20:03:36 - Initial decision log created with Phase 1 architectural decisions
