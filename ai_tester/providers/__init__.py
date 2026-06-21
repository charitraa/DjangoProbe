"""
AI Provider implementations for Django test generation.

Supported providers (NVIDIA is always first priority; the rest run only when
their API key is configured in the environment):
- NVIDIA: NVIDIA NIM (build.nvidia.com), OpenAI-compatible, free tier
- Anthropic: Claude models, supports custom base URLs
- Groq: Fast inference, free tier, remote API
- Gemini: Google AI models, fast and capable
- Together AI: Good free tier, reliable API
"""
from .base import BaseProvider
from .nvidia_provider import NvidiaProvider
from .anthropic_provider import AnthropicProvider
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider
from .together_provider import TogetherProvider
from .manager import ProviderManager

__all__ = [
    'BaseProvider',
    'NvidiaProvider',
    'AnthropicProvider',
    'GroqProvider',
    'GeminiProvider',
    'TogetherProvider',
    'ProviderManager',
]
