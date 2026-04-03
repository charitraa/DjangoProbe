"""
Base provider interface for AI services.
All AI providers must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from pathlib import Path


class BaseProvider(ABC):
    """
    Abstract base class for AI providers.

    All providers must implement these methods:
    - generate_text(): Generate text from a prompt
    - get_model_info(): Get information about available models
    - is_available(): Check if provider is accessible
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.model = model
        self.config = kwargs

    @abstractmethod
    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """
        Generate text from a prompt.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Generated text content
        """
        pass

    @abstractmethod
    def get_model_info(self) -> dict:
        """Get information about the provider's models."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is accessible and configured."""
        pass

    def get_provider_name(self) -> str:
        """Get the provider's display name."""
        return self.__class__.__name__.replace("Provider", "")

    def supports_streaming(self) -> bool:
        """Check if provider supports streaming responses."""
        return False