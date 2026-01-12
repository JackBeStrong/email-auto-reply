"""
Tests for reply formatter module
"""
import pytest
from app.reply_formatter import ReplyFormatter


class TestReplyFormatter:
    """Test ReplyFormatter class"""
    
    def test_is_sms_friendly_short(self):
        """Test SMS-friendly detection for short text"""
        short_text = "Thanks for your email! I'll get back to you soon."
        assert ReplyFormatter.is_sms_friendly(short_text) is True
    
    def test_is_sms_friendly_long(self):
        """Test SMS-friendly detection for long text"""
        long_text = "a" * 400
        assert ReplyFormatter.is_sms_friendly(long_text) is False
    
    def test_validate_reply_valid(self):
        """Test validation of valid reply"""
        valid_reply = "Thank you for your email. I'll review the document and get back to you by Friday."
        is_valid, error = ReplyFormatter.validate_reply(valid_reply)
        assert is_valid is True
        assert error is None
    
    def test_validate_reply_empty(self):
        """Test validation of empty reply"""
        is_valid, error = ReplyFormatter.validate_reply("")
        assert is_valid is False
        assert "empty" in error.lower()
    
    def test_validate_reply_too_short(self):
        """Test validation of too short reply"""
        is_valid, error = ReplyFormatter.validate_reply("Hi")
        assert is_valid is False
        assert "short" in error.lower()
    
    def test_validate_reply_with_placeholder(self):
        """Test validation detects placeholders"""
        reply_with_placeholder = "Dear [Your Name], thank you for your email."
        is_valid, error = ReplyFormatter.validate_reply(reply_with_placeholder)
        assert is_valid is False
        assert "placeholder" in error.lower()
    
    def test_extract_command_approve(self):
        """Test command extraction for approve"""
        command, draft_id, instruction = ReplyFormatter.extract_command("1")
        assert command == "approve"
        assert draft_id is None
        assert instruction is None
    
    def test_extract_command_approve_with_id(self):
        """Test command extraction for approve with draft ID"""
        command, draft_id, instruction = ReplyFormatter.extract_command("1 A7B2C3D4")
        assert command == "approve"
        assert draft_id == "A7B2C3D4"
        assert instruction is None
    
    def test_extract_command_edit_with_instruction(self):
        """Test command extraction for edit with instruction"""
        command, draft_id, instruction = ReplyFormatter.extract_command("2 make it more casual")
        assert command == "edit"
        assert draft_id is None
        assert instruction == "make it more casual"
    
    def test_extract_command_edit_with_id_and_instruction(self):
        """Test command extraction for edit with ID and instruction"""
        command, draft_id, instruction = ReplyFormatter.extract_command("2 A7B2C3D4 make it shorter")
        assert command == "edit"
        assert draft_id == "A7B2C3D4"
        assert instruction == "make it shorter"
    
    def test_extract_command_ignore(self):
        """Test command extraction for ignore"""
        command, draft_id, instruction = ReplyFormatter.extract_command("3")
        assert command == "ignore"
        assert draft_id is None
        assert instruction is None
    
    def test_extract_command_invalid(self):
        """Test command extraction for invalid command"""
        command, draft_id, instruction = ReplyFormatter.extract_command("invalid")
        assert command is None
        assert draft_id is None
        assert instruction is None
    
    def test_clean_reply_text(self):
        """Test reply text cleaning"""
        messy_text = "  Hello   world  \n\n\n\n  Test  "
        cleaned = ReplyFormatter.clean_reply_text(messy_text)
        assert cleaned == "Hello world\n\nTest"
    
    def test_format_for_sms_short(self):
        """Test SMS formatting for short reply"""
        sms = ReplyFormatter.format_for_sms(
            draft_id="A7B2C3D4",
            email_from="john@example.com",
            email_subject="Meeting tomorrow",
            reply_text="Yes, I'll be there at 2pm.",
            is_sms_friendly=True
        )
        assert "john@example.com" in sms
        assert "Meeting tomorrow" in sms
        assert "Yes, I'll be there at 2pm." in sms
        assert "1=Send 2=Edit 3=Ignore" in sms
        assert "#A7B2C3D4" in sms
    
    def test_format_for_sms_long(self):
        """Test SMS formatting for long reply"""
        long_reply = "a" * 500
        sms = ReplyFormatter.format_for_sms(
            draft_id="A7B2C3D4",
            email_from="john@example.com",
            email_subject="Project proposal",
            reply_text=long_reply,
            is_sms_friendly=False,
            short_summary="Thanks for the proposal...",
            web_url_base="https://reply.jackan.xyz"
        )
        assert "john@example.com" in sms
        assert "Preview:" in sms
        assert "Thanks for the proposal..." in sms
        assert "https://reply.jackan.xyz/d/A7B2C3D4" in sms
        assert "1=Send 2=Edit 3=Ignore" in sms
    
    def test_detect_language_english(self):
        """Test language detection for English"""
        english_text = "Thank you for your email. I will review the document."
        lang = ReplyFormatter.detect_language(english_text)
        assert lang == "en"
    
    def test_estimate_tokens(self):
        """Test token estimation"""
        text = "This is a test message with approximately twenty words in it for testing purposes."
        tokens = ReplyFormatter.estimate_tokens(text)
        assert tokens > 0
        assert tokens < len(text)  # Should be less than character count
