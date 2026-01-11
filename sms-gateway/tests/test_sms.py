"""Tests for SMS Gateway service."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import os

# Set test environment variables before importing app
os.environ.setdefault("ANDROID_GATEWAY_URL", "http://localhost:8080")
os.environ.setdefault("SMS_GATEWAY_USERNAME", "test")
os.environ.setdefault("SMS_GATEWAY_PASSWORD", "test")

from app.main import app, message_store
from app.models import MessageDirection, MessageStatus


@pytest.fixture
def client():
    """Create test client."""
    message_store.clear()
    return TestClient(app)


@pytest.fixture
def mock_sms_client():
    """Mock the SMS gateway client."""
    with patch("app.main.sms_client") as mock:
        mock.send_sms = AsyncMock(return_value=(True, "msg-123", None))
        mock.health_check = AsyncMock(return_value=True)
        yield mock


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, client, mock_sms_client):
        """Test health check returns status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestSendSMS:
    """Tests for sending SMS."""

    def test_send_sms_success(self, client, mock_sms_client):
        """Test successful SMS send."""
        response = client.post(
            "/sms/send",
            json={"to": "+14155551234", "message": "Hello, world!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message_id"] == "msg-123"

    def test_send_sms_stores_message(self, client, mock_sms_client):
        """Test that sent SMS is stored in history."""
        client.post(
            "/sms/send",
            json={"to": "+14155551234", "message": "Test message"},
        )
        assert len(message_store) == 1
        assert message_store[0].direction == MessageDirection.OUTGOING
        assert message_store[0].phone_number == "+14155551234"

    def test_send_sms_validation_empty_message(self, client, mock_sms_client):
        """Test validation rejects empty message."""
        response = client.post(
            "/sms/send",
            json={"to": "+14155551234", "message": ""},
        )
        assert response.status_code == 422

    def test_send_sms_failure(self, client, mock_sms_client):
        """Test SMS send failure handling."""
        mock_sms_client.send_sms = AsyncMock(
            return_value=(False, None, "Network error")
        )
        response = client.post(
            "/sms/send",
            json={"to": "+14155551234", "message": "Hello"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Network error"


class TestIncomingSMS:
    """Tests for incoming SMS webhook."""

    def test_incoming_sms_webhook(self, client):
        """Test incoming SMS is received and stored."""
        response = client.post(
            "/sms/incoming",
            json={
                "from": "+14155559999",
                "message": "1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert "message_id" in data

    def test_incoming_sms_stored(self, client):
        """Test incoming SMS is stored in message history."""
        client.post(
            "/sms/incoming",
            json={
                "from": "+14155559999",
                "message": "Approve reply",
            },
        )
        assert len(message_store) == 1
        assert message_store[0].direction == MessageDirection.INCOMING
        assert message_store[0].status == MessageStatus.RECEIVED

    def test_incoming_sms_with_device_id(self, client):
        """Test incoming SMS with device metadata."""
        client.post(
            "/sms/incoming",
            json={
                "from": "+14155559999",
                "message": "Test",
                "device_id": "android-001",
            },
        )
        assert message_store[0].metadata == {"device_id": "android-001"}


class TestSMSHistory:
    """Tests for SMS history endpoint."""

    def test_get_empty_history(self, client):
        """Test empty history returns empty list."""
        response = client.get("/sms/history")
        assert response.status_code == 200
        data = response.json()
        assert data["messages"] == []
        assert data["total"] == 0

    def test_get_history_with_messages(self, client, mock_sms_client):
        """Test history returns stored messages."""
        # Send some messages
        client.post("/sms/send", json={"to": "+1111", "message": "Outgoing"})
        client.post("/sms/incoming", json={"from": "+2222", "message": "Incoming"})

        response = client.get("/sms/history")
        data = response.json()
        assert data["total"] == 2
        assert len(data["messages"]) == 2

    def test_filter_by_direction(self, client, mock_sms_client):
        """Test filtering history by direction."""
        client.post("/sms/send", json={"to": "+1111", "message": "Out"})
        client.post("/sms/incoming", json={"from": "+2222", "message": "In"})

        response = client.get("/sms/history?direction=incoming")
        data = response.json()
        assert data["total"] == 1
        assert data["messages"][0]["direction"] == "incoming"

    def test_filter_by_phone_number(self, client, mock_sms_client):
        """Test filtering history by phone number."""
        client.post("/sms/send", json={"to": "+1111", "message": "First"})
        client.post("/sms/send", json={"to": "+2222", "message": "Second"})

        response = client.get("/sms/history?phone_number=%2B1111")
        data = response.json()
        assert data["total"] == 1

    def test_pagination(self, client, mock_sms_client):
        """Test history pagination."""
        for i in range(5):
            client.post("/sms/send", json={"to": f"+{i}", "message": f"Msg {i}"})

        response = client.get("/sms/history?page=1&page_size=2")
        data = response.json()
        assert data["total"] == 5
        assert len(data["messages"]) == 2
        assert data["page"] == 1


class TestGetMessage:
    """Tests for getting individual message."""

    def test_get_message_not_found(self, client):
        """Test 404 for non-existent message."""
        response = client.get("/sms/nonexistent-id")
        assert response.status_code == 404

    def test_get_message_success(self, client):
        """Test retrieving a specific message."""
        # Create a message
        response = client.post(
            "/sms/incoming",
            json={"from": "+1111", "message": "Test"},
        )
        message_id = response.json()["message_id"]

        # Retrieve it
        response = client.get(f"/sms/{message_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == message_id
        assert data["message"] == "Test"
