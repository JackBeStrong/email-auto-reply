"""
Tests for email filtering logic
"""
import pytest
from datetime import datetime
from app.models import EmailMessage, EmailFilter


def create_test_email(from_address: str, subject: str) -> EmailMessage:
    """Helper to create test email"""
    return EmailMessage(
        message_id="test-123",
        subject=subject,
        from_address=from_address,
        to_addresses=["recipient@example.com"],
        received_at=datetime.now()
    )


class TestEmailFilter:
    """Test email filtering logic"""
    
    def test_empty_filter_accepts_all(self):
        """Empty filter should accept all emails"""
        email_filter = EmailFilter()
        email = create_test_email("sender@example.com", "Test Subject")
        
        assert email_filter.should_process(email) is True
    
    def test_blacklist_sender_exact_match(self):
        """Blacklist should reject exact sender match"""
        email_filter = EmailFilter(blacklist_senders=["spam@example.com"])
        email = create_test_email("spam@example.com", "Test")
        
        assert email_filter.should_process(email) is False
    
    def test_blacklist_sender_domain(self):
        """Blacklist should reject domain match"""
        email_filter = EmailFilter(blacklist_senders=["@spam.com"])
        email = create_test_email("anyone@spam.com", "Test")
        
        assert email_filter.should_process(email) is False
    
    def test_blacklist_subject_keyword(self):
        """Blacklist should reject subject keyword match"""
        email_filter = EmailFilter(blacklist_subjects=["unsubscribe"])
        email = create_test_email("sender@example.com", "Click to unsubscribe")
        
        assert email_filter.should_process(email) is False
    
    def test_whitelist_sender_accepts(self):
        """Whitelist should accept matching sender"""
        email_filter = EmailFilter(
            whitelist_senders=["important@company.com"],
            blacklist_senders=["@company.com"]  # Domain blacklisted
        )
        email = create_test_email("important@company.com", "Test")
        
        # Whitelist takes precedence over blacklist
        assert email_filter.should_process(email) is True
    
    def test_whitelist_domain_accepts(self):
        """Whitelist should accept domain match"""
        email_filter = EmailFilter(whitelist_senders=["@company.com"])
        email = create_test_email("anyone@company.com", "Test")
        
        assert email_filter.should_process(email) is True
    
    def test_whitelist_rejects_non_matching(self):
        """Whitelist should reject non-matching senders"""
        email_filter = EmailFilter(whitelist_senders=["@company.com"])
        email = create_test_email("outsider@other.com", "Test")
        
        assert email_filter.should_process(email) is False
    
    def test_blacklist_priority_over_default(self):
        """Blacklist should take priority"""
        email_filter = EmailFilter(blacklist_senders=["noreply@"])
        email = create_test_email("noreply@example.com", "Test")
        
        assert email_filter.should_process(email) is False
    
    def test_case_insensitive_matching(self):
        """Filtering should be case-insensitive"""
        email_filter = EmailFilter(blacklist_senders=["SPAM@EXAMPLE.COM"])
        email = create_test_email("spam@example.com", "Test")
        
        assert email_filter.should_process(email) is False
    
    def test_multiple_rules(self):
        """Multiple rules should work together"""
        email_filter = EmailFilter(
            whitelist_senders=["@company.com"],
            blacklist_subjects=["newsletter", "promotion"]
        )
        
        # Whitelisted sender with blacklisted subject
        email1 = create_test_email("user@company.com", "Monthly Newsletter")
        assert email_filter.should_process(email1) is False  # Blacklist wins
        
        # Whitelisted sender with normal subject
        email2 = create_test_email("user@company.com", "Important Update")
        assert email_filter.should_process(email2) is True
        
        # Non-whitelisted sender
        email3 = create_test_email("user@other.com", "Normal Email")
        assert email_filter.should_process(email3) is False  # Not in whitelist


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
