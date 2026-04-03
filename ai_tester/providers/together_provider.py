"""
Together AI provider implementation.
Good free tier with reliable API.
"""
import os
from typing import List, Optional
from openai import OpenAI
from rich.console import Console

from .base import BaseProvider


class TogetherProvider(BaseProvider):
    """
    Together AI provider using OpenAI-compatible API.

    Free tier:
    - ~10,000-50,000 tokens/month (varies)
    - Good rate limits
    - Multiple quality models

    Models:
    - meta-llama/Llama-3.2-90b-chat-preview: Latest Llama, excellent quality
    - meta-llama/Llama-3.1-70b-chat: High quality, stable
    - mistralai/Mistral-7B-Instruct-v0.3: Fast, good performance
    - Qwen/Qwen2.5-72B-Instruct: Great for code generation
    """

    DEFAULT_MODEL = "meta-llama/Llama-3.1-8b-chat-Instruct-Turbo"
    BASE_URL = "https://api.together.xyz/v1"

    # Available models with characteristics
    MODELS = {
        "meta-llama/Llama-3.2-90b-chat-preview": {
            "quality": "excellent",
            "speed": "medium",
            "rate_limit": "medium",
            "description": "Latest Llama 3.2 90B, best quality"
        },
        "meta-llama/Llama-3.1-70b-chat": {
            "quality": "excellent",
            "speed": "medium",
            "rate_limit": "good",
            "description": "Llama 3.1 70B, very stable"
        },
        "meta-llama/Llama-3.1-8b-chat-Instruct-Turbo": {
            "quality": "good",
            "speed": "very_fast",
            "rate_limit": "high",
            "description": "Fast, high rate limits, recommended"
        },
        "mistralai/Mistral-7B-Instruct-v0.3": {
            "quality": "good",
            "speed": "fast",
            "rate_limit": "high",
            "description": "Mistral 7B, good performance"
        },
        "Qwen/Qwen2.5-72B-Instruct": {
            "quality": "excellent",
            "speed": "medium",
            "rate_limit": "good",
            "description": "Great for code generation"
        }
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, model=model, **kwargs)

        self.api_key = api_key or os.environ.get("TOGETHER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No Together API key found. Set TOGETHER_API_KEY environment variable.\n"
                "Get your free key at: https://api.together.xyz/"
            )

        self.model = model or self.DEFAULT_MODEL
        self.console = Console()

        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.BASE_URL,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Together client: {e}")

    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """
        Generate text using Together AI API.

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
            # Check for rate limit or quota errors
            if any(keyword in error_str.lower() for keyword in [
                "rate_limit", "quota", "429", "billing"
            ]):
                raise RateLimitError(f"Together rate/quota limit: {error_str}")
            raise RuntimeError(f"Together API error: {error_str}")

    def get_model_info(self) -> dict:
        """Get information about Together models."""
        return {
            "provider": "Together AI",
            "current_model": self.model,
            "available_models": self.MODELS,
            "base_url": self.BASE_URL,
            "is_free_tier": True,
            "is_available": self.is_available()
        }

    def is_available(self) -> bool:
        """Check if Together is accessible."""
        try:
            # Simple test request with minimal tokens
            self.generate_text([
                {"role": "user", "content": "hi"}
            ], max_tokens=5)
            return True
        except Exception:
            return False

    def supports_streaming(self) -> bool:
        """Together supports streaming."""
        return True


class RateLimitError(Exception):
    """Raised when Together rate/quota limit is hit."""
    pass