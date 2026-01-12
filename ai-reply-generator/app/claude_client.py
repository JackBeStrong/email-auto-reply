"""
Claude API client wrapper using Anthropic SDK
"""
import os
import logging
from typing import Optional, Tuple
from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError
from app.prompt_templates import PromptTemplates
from app.models import ToneType

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Wrapper for Claude API interactions"""
    
    # Model configuration
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
    MAX_TOKENS = 1024  # Maximum tokens for reply generation
    TEMPERATURE = 0.7  # Balance between creativity and consistency
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Claude API client
        
        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY must be provided or set in environment")
        
        self.client = Anthropic(api_key=self.api_key)
        self.prompt_templates = PromptTemplates()
    
    async def generate_reply(
        self,
        email_subject: str,
        email_from: str,
        email_body: str,
        tone: ToneType = ToneType.PROFESSIONAL,
        thread_context: Optional[str] = None,
        context_instructions: Optional[str] = None,
        max_length: Optional[int] = None
    ) -> Tuple[str, int]:
        """
        Generate a reply using Claude API
        
        Args:
            email_subject: Subject line of the email
            email_from: Sender's email address
            email_body: Body text of the email
            tone: Desired tone for the reply
            thread_context: Previous emails in the thread (optional)
            context_instructions: Additional context or instructions (optional)
            max_length: Maximum length constraint in characters (optional)
            
        Returns:
            Tuple of (reply_text, tokens_used)
            
        Raises:
            APIError: If Claude API returns an error
            APIConnectionError: If connection to Claude API fails
            RateLimitError: If rate limit is exceeded
        """
        try:
            # Build the prompt
            prompt = self.prompt_templates.build_reply_prompt(
                email_subject=email_subject,
                email_from=email_from,
                email_body=email_body,
                tone=tone,
                thread_context=thread_context,
                context_instructions=context_instructions,
                max_length=max_length
            )
            
            logger.info(f"Generating reply for email from {email_from}")
            logger.debug(f"Prompt: {prompt[:200]}...")
            
            # Call Claude API
            message = self.client.messages.create(
                model=self.DEFAULT_MODEL,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
                system=self.prompt_templates.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract reply text
            reply_text = message.content[0].text.strip()
            
            # Calculate total tokens used
            tokens_used = message.usage.input_tokens + message.usage.output_tokens
            
            logger.info(f"Generated reply: {len(reply_text)} chars, {tokens_used} tokens")
            logger.debug(f"Reply: {reply_text[:100]}...")
            
            return reply_text, tokens_used
            
        except RateLimitError as e:
            logger.error(f"Rate limit exceeded: {e}")
            raise
        except APIConnectionError as e:
            logger.error(f"Connection error to Claude API: {e}")
            raise
        except APIError as e:
            logger.error(f"Claude API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating reply: {e}")
            raise
    
    async def generate_summary(self, full_draft: str, max_length: int = 150) -> Tuple[str, int]:
        """
        Generate a short summary of a reply draft
        
        Args:
            full_draft: The full reply text
            max_length: Maximum length for the summary (default 150 chars)
            
        Returns:
            Tuple of (summary_text, tokens_used)
            
        Raises:
            APIError: If Claude API returns an error
        """
        try:
            prompt = self.prompt_templates.build_summary_prompt(full_draft, max_length)
            
            logger.info(f"Generating summary for draft ({len(full_draft)} chars)")
            
            message = self.client.messages.create(
                model=self.DEFAULT_MODEL,
                max_tokens=100,  # Summaries are short
                temperature=0.5,  # More deterministic for summaries
                system="You are a concise summarizer. Generate brief, clear summaries.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            summary_text = message.content[0].text.strip()
            tokens_used = message.usage.input_tokens + message.usage.output_tokens
            
            # Ensure summary doesn't exceed max_length
            if len(summary_text) > max_length:
                summary_text = summary_text[:max_length-3] + "..."
            
            logger.info(f"Generated summary: {len(summary_text)} chars, {tokens_used} tokens")
            
            return summary_text, tokens_used
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            # Fallback: use first N characters of draft
            fallback_summary = full_draft[:max_length-3] + "..." if len(full_draft) > max_length else full_draft
            logger.warning(f"Using fallback summary: {fallback_summary[:50]}...")
            return fallback_summary, 0
    
    async def detect_tone(self, email_body: str) -> ToneType:
        """
        Detect the appropriate tone for a reply based on the email content
        
        Args:
            email_body: Body text of the email
            
        Returns:
            Detected ToneType
        """
        try:
            prompt = self.prompt_templates.build_tone_detection_prompt(email_body)
            
            logger.info("Detecting email tone")
            
            message = self.client.messages.create(
                model=self.DEFAULT_MODEL,
                max_tokens=10,
                temperature=0.3,  # More deterministic for classification
                system="You are a tone analyzer. Classify email tones accurately.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            tone_str = message.content[0].text.strip().lower()
            
            # Map response to ToneType
            tone_mapping = {
                "professional": ToneType.PROFESSIONAL,
                "casual": ToneType.CASUAL,
                "technical": ToneType.TECHNICAL,
                "friendly": ToneType.FRIENDLY
            }
            
            detected_tone = tone_mapping.get(tone_str, ToneType.PROFESSIONAL)
            logger.info(f"Detected tone: {detected_tone.value}")
            
            return detected_tone
            
        except Exception as e:
            logger.error(f"Error detecting tone: {e}")
            # Default to professional tone
            return ToneType.PROFESSIONAL
    
    def check_health(self) -> bool:
        """
        Check if Claude API is accessible
        
        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Simple test call with minimal tokens
            message = self.client.messages.create(
                model=self.DEFAULT_MODEL,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Hello"}
                ]
            )
            return True
        except Exception as e:
            logger.error(f"Claude API health check failed: {e}")
            return False
