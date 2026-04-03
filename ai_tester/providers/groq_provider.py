"""
Groq AI provider implementation.
Fast inference with good free tier.
"""
import os
from typing import List, Optional
from openai import OpenAI
from rich.console import Console

from .base import BaseProvider


class GroqProvider(BaseProvider):
    """
    Groq AI provider using OpenAI-compatible API.

    Free tier:
    - 14,400 requests per day
    - 30 requests per minute
    - Very fast inference

    Models:
    - llama-3.3-70b-versatile: Best quality, lower rate limits
    - llama-3.1-8b-instant: Fast, higher rate limits
    - gemma2-9b-it: Google model, good performance
    """

    DEFAULT_MODEL = "llama-3.1-8b-instant"
    BASE_URL = "https://api.groq.com/openai/v1"

    # Available models with characteristics
    MODELS = {
        "llama-3.3-70b-versatile": {
            "quality": "high",
            "speed": "fast",
            "rate_limit": "lower",
            "description": "Best quality, slower rate limits"
        },
        "llama-3.1-8b-instant": {
            "quality": "medium",
            "speed": "very_fast",
            "rate_limit": "higher",
            "description": "Fast, higher rate limits"
        },
        "gemma2-9b-it": {
            "quality": "medium",
            "speed": "fast",
            "rate_limit": "higher",
            "description": "Google model, good performance"
        }
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, model=model, **kwargs)

        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            # Try numbered keys
            for i in range(1, 4):
                key = os.environ.get(f"GROQ_API_KEY_{i}")
                if key:
                    self.api_key = key
                    break

        if not self.api_key:
            raise ValueError("No Groq API key found. Set GROQ_API_KEY environment variable.")

        self.model = model or self.DEFAULT_MODEL
        self.console = Console()

        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.BASE_URL,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Groq client: {e}")

    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """
        Generate text using Groq API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Generated text content
        """
        default_params = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 8096),
            "temperature": kwargs.get("temperature", 0.7),
        }

        # Override with any explicitly passed parameters
        for key, value in kwargs.items():
            if key in ["model", "max_tokens", "temperature"]:
                default_params[key] = value

        try:
            response = self.client.chat.completions.create(
                messages=messages,
                **default_params
            )
            return response.choices[0].message.content
        except Exception as e:
            error_str = str(e)
            # Check for rate limit errors
            if any(keyword in error_str.lower() for keyword in [
                "rate_limit", "413", "429", "over capacity", "503"
            ]):
                raise RateLimitError(f"Groq rate limit: {error_str}")
            raise RuntimeError(f"Groq API error: {error_str}")

    def get_model_info(self) -> dict:
        """Get information about Groq models."""
        return {
            "provider": "Groq",
            "current_model": self.model,
            "available_models": self.MODELS,
            "base_url": self.BASE_URL,
            "is_free_tier": True,
            "is_available": self.is_available()
        }

    def is_available(self) -> bool:
        """Check if Groq is accessible."""
        try:
            # Simple test request
            self.generate_text([
                {"role": "user", "content": "ping"}
            ], max_tokens=10)
            return True
        except Exception:
            return False

    def supports_streaming(self) -> bool:
        """Groq supports streaming."""
        return True


class RateLimitError(Exception):
    """Raised when Groq rate limit is hit."""
    pass