"""
Prompt templates for Claude API reply generation
"""
from typing import Optional
from app.models import ToneType


class PromptTemplates:
    """Manages prompt templates for different reply generation scenarios"""
    
    # Base system prompt for reply generation
    SYSTEM_PROMPT = """You are an email assistant helping to draft professional email replies. 
Your goal is to generate concise, contextually appropriate responses that address the sender's main points.

Key principles:
- Be clear and direct
- Match the tone of the original email
- Keep replies brief but complete (2-4 sentences ideal)
- Include appropriate greeting and closing
- Never use placeholders like [Your Name] or [Company]
- Generate ONLY the reply text, no explanations or meta-commentary"""

    # Tone-specific instructions
    TONE_INSTRUCTIONS = {
        ToneType.PROFESSIONAL: "Use formal, business-appropriate language. Be polite and respectful.",
        ToneType.CASUAL: "Use friendly, conversational language. Be warm but still professional.",
        ToneType.TECHNICAL: "Use precise technical language. Be detailed and specific about technical matters.",
        ToneType.FRIENDLY: "Use warm, personable language. Show enthusiasm and positivity."
    }
    
    @staticmethod
    def build_reply_prompt(
        email_subject: str,
        email_from: str,
        email_body: str,
        tone: ToneType = ToneType.PROFESSIONAL,
        thread_context: Optional[str] = None,
        context_instructions: Optional[str] = None,
        max_length: Optional[int] = None
    ) -> str:
        """
        Build a complete prompt for reply generation
        
        Args:
            email_subject: Subject line of the email
            email_from: Sender's email address
            email_body: Body text of the email
            tone: Desired tone for the reply
            thread_context: Previous emails in the thread (optional)
            context_instructions: Additional context or instructions (optional)
            max_length: Maximum length constraint in characters (optional)
            
        Returns:
            Complete prompt string for Claude API
        """
        prompt_parts = []
        
        # Email context
        prompt_parts.append(f"Subject: {email_subject}")
        prompt_parts.append(f"From: {email_from}")
        prompt_parts.append("")
        
        # Thread context if available
        if thread_context:
            prompt_parts.append("Previous conversation:")
            prompt_parts.append(thread_context)
            prompt_parts.append("")
            prompt_parts.append("Latest email:")
        else:
            prompt_parts.append("Email to reply to:")
        
        prompt_parts.append(email_body)
        prompt_parts.append("")
        
        # Instructions
        prompt_parts.append("---")
        prompt_parts.append("")
        prompt_parts.append(f"Generate a reply with a {tone.value} tone.")
        prompt_parts.append(PromptTemplates.TONE_INSTRUCTIONS[tone])
        prompt_parts.append("")
        
        # Length constraint
        if max_length:
            prompt_parts.append(f"Keep the reply under {max_length} characters.")
        else:
            prompt_parts.append("Keep the reply concise (2-4 sentences ideal, but adjust based on the email's complexity).")
        
        # Additional context
        if context_instructions:
            prompt_parts.append("")
            prompt_parts.append("Additional context:")
            prompt_parts.append(context_instructions)
        
        prompt_parts.append("")
        prompt_parts.append("Generate ONLY the reply text (no subject line, no explanations):")
        
        return "\n".join(prompt_parts)
    
    @staticmethod
    def build_summary_prompt(full_draft: str, max_length: int = 150) -> str:
        """
        Build a prompt to generate a short summary of a reply draft
        
        Args:
            full_draft: The full reply text
            max_length: Maximum length for the summary (default 150 chars)
            
        Returns:
            Prompt string for summary generation
        """
        return f"""Generate a very brief summary of this email reply in {max_length} characters or less.
The summary should capture the main point or action.

Full reply:
{full_draft}

Generate ONLY the summary text (no quotes, no explanations):"""

    @staticmethod
    def build_tone_detection_prompt(email_body: str) -> str:
        """
        Build a prompt to detect the appropriate tone for a reply
        
        Args:
            email_body: Body text of the email
            
        Returns:
            Prompt string for tone detection
        """
        return f"""Analyze this email and determine the most appropriate reply tone.
Choose ONE of: professional, casual, technical, friendly

Email:
{email_body}

Respond with ONLY the tone word (no explanation):"""
