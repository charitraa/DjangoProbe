"""
Google Gemini AI provider implementation.
Supports Gemini models via OpenAI-compatible API.
"""
import os
from typing import List, Optional
from openai import OpenAI
from rich.console import Console

from .base import BaseProvider


class GeminiProvider(BaseProvider):
    """
    Google Gemini provider using OpenAI-compatible API.

    Models:
    - gemini-2.0-flash-exp: Latest, very fast
    - gemini-1.5-pro: High quality, good performance
    - gemini-1.5-flash: Fast, good quality
    - gemini-1.5-flash-8b: Lightweight, very fast

    Requires GEMINI_API_KEY environment variable.
    """

    DEFAULT_MODEL = "gemini-2.0-flash-exp"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    # Available models with characteristics
    MODELS = {
        "gemini-2.0-flash-exp": {
            "quality": "excellent",
            "speed": "very_fast",
            "rate_limit": "good",
            "description": "Latest Gemini 2.0, very fast"
        },
        "gemini-1.5-pro": {
            "quality": "excellent",
            "speed": "fast",
            "rate_limit": "good",
            "description": "High quality, stable"
        },
        "gemini-1.5-flash": {
            "quality": "good",
            "speed": "fast",
            "rate_limit": "high",
            "description": "Fast, good quality"
        },
        "gemini-1.5-flash-8b": {
            "quality": "good",
            "speed": "very_fast",
            "rate_limit": "high",
            "description": "Lightweight, very fast"
        }
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, model=model, **kwargs)

        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No Gemini API key found. Set GEMINI_API_KEY environment variable.\n"
                "Get your key at: https://makersuite.google.com/app/apikey"
            )

        self.model = model or self.DEFAULT_MODEL
        self.console = Console()

        try:
            # Use OpenAI-compatible API for Gemini
            # Model name needs to be prefixed for OpenAI API
            model_name = self.model if self.model.startswith("models/") else f"models/{self.model}"

            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.BASE_URL + "/openai/",
            )
            self.model_for_api = model_name
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Gemini client: {e}")

    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """
        Generate text using Gemini API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Generated text content
        """
        default_params = {
            "model": self.model_for_api,
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
            # Check for rate limit or quota errors
            if any(keyword in error_str.lower() for keyword in [
                "rate_limit", "quota", "429", "billing", "resource_exhausted"
            ]):
                raise RateLimitError(f"Gemini rate/quota limit: {error_str}")
            raise RuntimeError(f"Gemini API error: {error_str}")

    def get_model_info(self) -> dict:
        """Get information about Gemini models."""
        return {
            "provider": "Gemini",
            "current_model": self.model,
            "available_models": self.MODELS,
            "base_url": self.BASE_URL,
            "is_free_tier": True,
            "is_available": self.is_available()
        }

    def is_available(self) -> bool:
        """Check if Gemini is configured and accessible."""
        try:
            # Check if API key is present and client is initialized
            if not self.api_key or not hasattr(self, 'client'):
                return False
            # Basic configuration check - don't make live API call
            # Actual errors will be caught when generating text
            return bool(self.api_key and self.api_key.startswith('AIza'))
        except Exception:
            return False

    def supports_streaming(self) -> bool:
        """Gemini supports streaming."""
        return True


class RateLimitError(Exception):
    """Raised when Gemini rate/quota limit is hit."""
    pass
