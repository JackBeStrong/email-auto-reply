"""
SMS Command Parser

Parses user SMS responses and extracts commands and edit instructions.
"""
import re
from app.models import ParsedCommand


class CommandParser:
    """Parse SMS commands from user responses"""
    
    # Command patterns
    APPROVE_PATTERNS = [
        r'^1$',
        r'^approve$',
        r'^send$',
        r'^yes$',
        r'^ok$',
    ]
    
    EDIT_PATTERNS = [
        r'^2\s+(.+)$',  # "2 <instructions>"
        r'^edit\s+(.+)$',  # "edit <instructions>"
    ]
    
    IGNORE_PATTERNS = [
        r'^3$',
        r'^ignore$',
        r'^skip$',
        r'^no$',
    ]
    
    def parse(self, message: str) -> ParsedCommand:
        """
        Parse an SMS message and extract the command.
        
        Args:
            message: The SMS message text
            
        Returns:
            ParsedCommand with command_type and optional edit_instructions
        """
        # Normalize message: strip whitespace and convert to lowercase
        normalized = message.strip().lower()
        
        # Check for approve command
        for pattern in self.APPROVE_PATTERNS:
            if re.match(pattern, normalized, re.IGNORECASE):
                return ParsedCommand(
                    command_type='approve',
                    edit_instructions=None,
                    raw_message=message
                )
        
        # Check for edit command with instructions
        for pattern in self.EDIT_PATTERNS:
            match = re.match(pattern, normalized, re.IGNORECASE)
            if match:
                instructions = match.group(1).strip()
                return ParsedCommand(
                    command_type='edit',
                    edit_instructions=instructions,
                    raw_message=message
                )
        
        # Check for ignore command
        for pattern in self.IGNORE_PATTERNS:
            if re.match(pattern, normalized, re.IGNORECASE):
                return ParsedCommand(
                    command_type='ignore',
                    edit_instructions=None,
                    raw_message=message
                )
        
        # Unknown command
        return ParsedCommand(
            command_type='unknown',
            edit_instructions=None,
            raw_message=message
        )
    
    def is_valid_command(self, message: str) -> bool:
        """
        Check if a message is a valid command.
        
        Args:
            message: The SMS message text
            
        Returns:
            True if the message is a valid command, False otherwise
        """
        parsed = self.parse(message)
        return parsed.command_type != 'unknown'
    
    def get_help_text(self) -> str:
        """
        Get help text explaining available commands.
        
        Returns:
            Help text string
        """
        return (
            "Commands:\n"
            "1 or 'send' - Send the draft reply\n"
            "2 <instructions> - Edit reply (e.g., '2 make it more casual')\n"
            "3 or 'ignore' - Don't reply to this email"
        )
