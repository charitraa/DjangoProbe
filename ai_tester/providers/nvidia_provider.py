"""
NVIDIA NIM AI provider implementation.

NVIDIA's build platform (https://build.nvidia.com) exposes an
OpenAI-compatible inference endpoint with a generous free tier, which makes it
a drop-in replacement when the Groq/Gemini free quotas are exhausted.
"""
import os
from typing import List, Optional
from openai import OpenAI
from rich.console import Console

from .base import BaseProvider


class NvidiaProvider(BaseProvider):
    """
    NVIDIA NIM provider using the OpenAI-compatible API.

    Get a free API key at https://build.nvidia.com (keys start with 'nvapi-').

    Recommended models for DjangoProbe (large, structured code-generation prompts):
    - qwen/qwen3.5-122b-a10b: coding/reasoning MoE, best fit for test generation
    - qwen/qwen3-next-80b-a3b-instruct: instruct, long context (good alternate)
    """

    # qwen3.5-122b-a10b is described on build.nvidia.com as a coding/reasoning
    # model with a free endpoint — the best available fit for emitting a
    # complete Django TestCase file under DjangoProbe's large guardrail prompt.
    DEFAULT_MODEL = "qwen/qwen3.5-122b-a10b"
    BASE_URL = "https://integrate.api.nvidia.com/v1"

    MODELS = {
        "qwen/qwen3.5-122b-a10b": {
            "quality": "high",
            "speed": "fast",
            "description": "122B MoE (10B active), coding/reasoning, free endpoint",
        },
        "qwen/qwen3-next-80b-a3b-instruct": {
            "quality": "high",
            "speed": "fast",
            "description": "Instruct, ultra-long context, free endpoint",
        },
        "qwen/qwen3.5-397b-a17b": {
            "quality": "high",
            "speed": "medium",
            "description": "400B MoE VLM, agentic, free endpoint",
        },
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, model=model, **kwargs)

        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No NVIDIA API key found. Set NVIDIA_API_KEY environment variable. "
                "Get a free key at https://build.nvidia.com"
            )

        self.model = model or os.environ.get("NVIDIA_MODEL") or self.DEFAULT_MODEL
        # Allow overriding the endpoint (any OpenAI-compatible server, e.g. a
        # proxy or a local model). Defaults to NVIDIA NIM.
        self.base_url = os.environ.get("NVIDIA_BASE_URL") or self.BASE_URL
        self.console = Console()

        try:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize NVIDIA client: {e}")

    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """Generate text using the NVIDIA NIM API."""
        default_params = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 8096),
            "temperature": kwargs.get("temperature", 0.7),
        }
        for key, value in kwargs.items():
            if key in ["model", "max_tokens", "temperature"]:
                default_params[key] = value

        try:
            response = self.client.chat.completions.create(
                messages=messages,
                **default_params,
            )
            return response.choices[0].message.content
        except Exception as e:
            error_str = str(e)
            if any(keyword in error_str.lower() for keyword in [
                "rate_limit", "rate limit", "413", "429", "over capacity", "503",
                "too many requests",
            ]):
                raise RateLimitError(f"NVIDIA rate limit: {error_str}")
            raise RuntimeError(f"NVIDIA API error: {error_str}")

    def get_model_info(self) -> dict:
        """Get information about NVIDIA models."""
        return {
            "provider": "NVIDIA",
            "current_model": self.model,
            "available_models": self.MODELS,
            "base_url": self.base_url,
            "is_free_tier": True,
            "is_available": self.is_available(),
        }

    def is_available(self) -> bool:
        """Check if NVIDIA is configured (no live API call to preserve quota)."""
        try:
            if not self.api_key or not hasattr(self, "client"):
                return False
            return bool(self.api_key.startswith("nvapi-"))
        except Exception:
            return False

    def supports_streaming(self) -> bool:
        """NVIDIA NIM supports streaming."""
        return True


class RateLimitError(Exception):
    """Raised when the NVIDIA rate limit is hit."""
    pass
