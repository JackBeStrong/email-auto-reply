"""
Orchestrator Service - Email Auto-Reply System Phase 4

This service coordinates the entire email auto-reply workflow:
- Polls Email Monitor for pending emails
- Requests AI-generated replies
- Sends SMS notifications with draft replies
- Handles user responses (approve/edit/ignore)
- Implements iterative edit workflow
- Sends approved replies via Gmail SMTP
"""

__version__ = "1.0.0"
