"""
Anthropic AI provider implementation.
Supports Claude models with custom base URL.
"""
import os
from typing import List, Optional
from anthropic import Anthropic
from rich.console import Console

from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """
    Anthropic provider using Claude models.

    Models:
    - claude-3.5-sonnet: Best quality, fast
    - claude-3.5-haiku: Lightweight, very fast
    - claude-3-opus: Highest quality, slower

    Supports custom base URLs for proxy services.
    """

    DEFAULT_MODEL = "claude-3.5-sonnet"

    # Available models with characteristics
    MODELS = {
        "claude-3.5-sonnet": {
            "quality": "excellent",
            "speed": "fast",
            "rate_limit": "good",
            "description": "Best balance of quality and speed"
        },
        "claude-3.5-haiku": {
            "quality": "good",
            "speed": "very_fast",
            "rate_limit": "high",
            "description": "Lightweight, very fast"
        },
        "claude-3-opus": {
            "quality": "highest",
            "speed": "slower",
            "rate_limit": "lower",
            "description": "Highest quality, but slower"
        }
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, model=model, **kwargs)

        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY environment variable."
            )

        self.model = model or self.DEFAULT_MODEL
        self.base_url = kwargs.get("base_url") or os.environ.get("ANTHROPIC_BASE_URL")
        self.console = Console()

        try:
            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            self.client = Anthropic(**client_kwargs)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Anthropic client: {e}")

    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """
        Generate text using Anthropic API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Generated text content
        """
        # Extract system message and convert to Anthropic format
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                # Anthropic expects system as a separate parameter
                system_prompt = msg.get("content", "")
            elif msg.get("role") in ["user", "assistant"]:
                # Only include user/assistant messages
                anthropic_messages.append(msg)

        default_params = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 8096),
            "temperature": kwargs.get("temperature", 0.7),
            "messages": anthropic_messages,
        }

        # Add system prompt if present
        if system_prompt:
            default_params["system"] = system_prompt

        # Override with any explicitly passed parameters
        for key, value in kwargs.items():
            if key in ["model", "max_tokens", "temperature"]:
                default_params[key] = value

        try:
            response = self.client.messages.create(**default_params)
            return response.content[0].text
        except Exception as e:
            error_str = str(e)
            # Check for rate limit or quota errors
            if any(keyword in error_str.lower() for keyword in [
                "rate_limit", "quota", "429", "billing", "overloaded"
            ]):
                raise RateLimitError(f"Anthropic rate/quota limit: {error_str}")
            raise RuntimeError(f"Anthropic API error: {error_str}")

    def get_model_info(self) -> dict:
        """Get information about Anthropic models."""
        return {
            "provider": "Anthropic",
            "current_model": self.model,
            "available_models": self.MODELS,
            "base_url": self.base_url,
            "is_free_tier": False,
            "is_available": self.is_available()
        }

    def is_available(self) -> bool:
        """Check if Anthropic is configured and accessible."""
        try:
            # Check if API key is present and client is initialized (NO live API call)
            if not self.api_key or not hasattr(self, 'client'):
                return False
            # Basic configuration check only - don't waste API quota
            return bool(self.api_key and len(self.api_key) > 10)
        except Exception:
            return False

    def supports_streaming(self) -> bool:
        """Anthropic supports streaming."""
        return True


class RateLimitError(Exception):
    """Raised when Anthropic rate/quota limit is hit."""
    pass
