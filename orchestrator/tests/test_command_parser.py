"""
Tests for SMS command parser
"""
import pytest
from app.command_parser import CommandParser


@pytest.fixture
def parser():
    """Create command parser instance"""
    return CommandParser()


class TestApproveCommands:
    """Test approve command parsing"""
    
    def test_approve_with_1(self, parser):
        result = parser.parse("1")
        assert result.command_type == "approve"
        assert result.edit_instructions is None
    
    def test_approve_with_send(self, parser):
        result = parser.parse("send")
        assert result.command_type == "approve"
        assert result.edit_instructions is None
    
    def test_approve_with_approve(self, parser):
        result = parser.parse("approve")
        assert result.command_type == "approve"
        assert result.edit_instructions is None
    
    def test_approve_with_yes(self, parser):
        result = parser.parse("yes")
        assert result.command_type == "approve"
        assert result.edit_instructions is None
    
    def test_approve_with_ok(self, parser):
        result = parser.parse("ok")
        assert result.command_type == "approve"
        assert result.edit_instructions is None
    
    def test_approve_case_insensitive(self, parser):
        result = parser.parse("SEND")
        assert result.command_type == "approve"
        
        result = parser.parse("Yes")
        assert result.command_type == "approve"


class TestEditCommands:
    """Test edit command parsing"""
    
    def test_edit_with_2_and_instructions(self, parser):
        result = parser.parse("2 make it more casual")
        assert result.command_type == "edit"
        assert result.edit_instructions == "make it more casual"
    
    def test_edit_with_edit_keyword(self, parser):
        result = parser.parse("edit reject meeting with health reason")
        assert result.command_type == "edit"
        assert result.edit_instructions == "reject meeting with health reason"
    
    def test_edit_with_complex_instructions(self, parser):
        result = parser.parse("2 say I'm busy and suggest next week instead")
        assert result.command_type == "edit"
        assert result.edit_instructions == "say i'm busy and suggest next week instead"
    
    def test_edit_case_insensitive(self, parser):
        result = parser.parse("EDIT make it shorter")
        assert result.command_type == "edit"
        assert result.edit_instructions == "make it shorter"
    
    def test_edit_with_extra_whitespace(self, parser):
        result = parser.parse("2   make it more formal  ")
        assert result.command_type == "edit"
        assert result.edit_instructions == "make it more formal"


class TestIgnoreCommands:
    """Test ignore command parsing"""
    
    def test_ignore_with_3(self, parser):
        result = parser.parse("3")
        assert result.command_type == "ignore"
        assert result.edit_instructions is None
    
    def test_ignore_with_ignore(self, parser):
        result = parser.parse("ignore")
        assert result.command_type == "ignore"
        assert result.edit_instructions is None
    
    def test_ignore_with_skip(self, parser):
        result = parser.parse("skip")
        assert result.command_type == "ignore"
        assert result.edit_instructions is None
    
    def test_ignore_with_no(self, parser):
        result = parser.parse("no")
        assert result.command_type == "ignore"
        assert result.edit_instructions is None
    
    def test_ignore_case_insensitive(self, parser):
        result = parser.parse("IGNORE")
        assert result.command_type == "ignore"
        
        result = parser.parse("Skip")
        assert result.command_type == "ignore"


class TestUnknownCommands:
    """Test unknown command handling"""
    
    def test_unknown_random_text(self, parser):
        result = parser.parse("hello world")
        assert result.command_type == "unknown"
        assert result.edit_instructions is None
    
    def test_unknown_number(self, parser):
        result = parser.parse("4")
        assert result.command_type == "unknown"
    
    def test_unknown_empty(self, parser):
        result = parser.parse("")
        assert result.command_type == "unknown"
    
    def test_edit_without_instructions(self, parser):
        # "2" alone without instructions should be unknown
        result = parser.parse("2")
        assert result.command_type == "unknown"


class TestValidation:
    """Test command validation"""
    
    def test_is_valid_command_approve(self, parser):
        assert parser.is_valid_command("1") is True
        assert parser.is_valid_command("send") is True
    
    def test_is_valid_command_edit(self, parser):
        assert parser.is_valid_command("2 make it casual") is True
        assert parser.is_valid_command("edit be more formal") is True
    
    def test_is_valid_command_ignore(self, parser):
        assert parser.is_valid_command("3") is True
        assert parser.is_valid_command("ignore") is True
    
    def test_is_valid_command_unknown(self, parser):
        assert parser.is_valid_command("hello") is False
        assert parser.is_valid_command("4") is False
        assert parser.is_valid_command("") is False


class TestHelpText:
    """Test help text generation"""
    
    def test_get_help_text(self, parser):
        help_text = parser.get_help_text()
        assert "1" in help_text
        assert "2" in help_text
        assert "3" in help_text
        assert "send" in help_text.lower()
        assert "edit" in help_text.lower()
        assert "ignore" in help_text.lower()


class TestRawMessage:
    """Test that raw message is preserved"""
    
    def test_raw_message_preserved(self, parser):
        original = "2 Make It More Casual"
        result = parser.parse(original)
        assert result.raw_message == original
    
    def test_raw_message_with_whitespace(self, parser):
        original = "  1  "
        result = parser.parse(original)
        assert result.raw_message == original
