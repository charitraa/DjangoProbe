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
            for i in range(1, 6):
                key = os.environ.get(f"GROQ_API_KEY_{i}")
                if key:
                    self.api_key = key
                    break

        if not self.api_key:
            raise ValueError("No Groq API key found. Set GROQ_API_KEY environment variable.")

        # Store all available API keys for rotation
        self.api_keys = []
        primary = self.api_key
        self.api_keys.append(primary)
        for i in range(1, 6):
            key = os.environ.get(f"GROQ_API_KEY_{i}")
            if key and key != primary and key not in self.api_keys:
                self.api_keys.append(key)
        self._current_key_index = 0

        self.model = model or self.DEFAULT_MODEL
        self.console = Console()

        try:
            self.client = OpenAI(
                api_key=self.api_keys[self._current_key_index],
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
                # Try rotating to next API key
                if self._rotate_api_key():
                    self.console.print(f"[cyan]↻ Rotated to next Groq API key ({self._current_key_index + 1}/{len(self.api_keys)})[/cyan]")
                    try:
                        response = self.client.chat.completions.create(
                            messages=messages,
                            **default_params
                        )
                        return response.choices[0].message.content
                    except Exception:
                        pass
                raise RateLimitError(f"Groq rate limit (all {len(self.api_keys)} keys exhausted): {error_str}")
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
        """Check if Groq is configured and accessible."""
        try:
            # Check if API key is present and client is initialized (NO live API call)
            if not self.api_keys or not hasattr(self, 'client'):
                return False
            # Basic configuration check only - don't waste rate limit quota
            return bool(self.api_keys[0] and self.api_keys[0].startswith('gsk_'))
        except Exception:
            return False

    def _rotate_api_key(self) -> bool:
        """Rotate to next available API key."""
        if len(self.api_keys) <= 1:
            return False
        next_index = (self._current_key_index + 1) % len(self.api_keys)
        if next_index == self._current_key_index:
            return False
        self._current_key_index = next_index
        new_key = self.api_keys[self._current_key_index]
        self.client.api_key = new_key
        return True

    def supports_streaming(self) -> bool:
        """Groq supports streaming."""
        return True


class RateLimitError(Exception):
    """Raised when Groq rate limit is hit."""
    pass