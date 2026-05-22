"""
Provider manager for multi-provider AI support with automatic fallback.
"""
import os
import time
from typing import List, Optional, Dict, Any
from rich.console import Console

from .base import BaseProvider
from .groq_provider import GroqProvider, RateLimitError as GroqRateLimitError
from .ollama_provider import OllamaProvider
from .together_provider import TogetherProvider, RateLimitError as TogetherRateLimitError
from .anthropic_provider import AnthropicProvider, RateLimitError as AnthropicRateLimitError
from .gemini_provider import GeminiProvider, RateLimitError as GeminiRateLimitError


class ProviderManager:
    """
    Manages multiple AI providers with automatic fallback.

    Features:
    - Automatic provider rotation on failures
    - Rate limit handling with exponential backoff
    - Priority-based provider selection
    - Health checking for providers
    - Configurable retry logic

    Usage:
        manager = ProviderManager(repo_path)
        response = manager.generate_text(messages)
    """

    def __init__(self, repo_path: str, analysis=None):
        self.repo_path = repo_path
        self.analysis = analysis
        self.console = Console()

        # Load configuration
        self.config = self._load_config()

        # Initialize providers in priority order
        self.providers = self._initialize_providers()

        if not self.providers:
            raise RuntimeError(
                "No AI providers available. Please configure at least one provider:\n"
                "  - Groq: Set GROQ_API_KEY in .env\n"
                "  - Ollama: Install and run 'ollama serve'\n"
                "  - Together: Set TOGETHER_API_KEY in .env"
            )

        # Current provider index
        self.current_provider_index = 0

        # Provider health tracking
        self.provider_health = {i: {"failures": 0, "last_used": 0} for i in range(len(self.providers))}

        self._print_status()

    def _load_config(self) -> Dict[str, Any]:
        """Load provider configuration from environment."""
        return {
            "preferred_provider": os.environ.get("AI_PREFERRED_PROVIDER", "auto"),
            "groq_model": os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
            "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
            "together_model": os.environ.get("TOGETHER_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"),
            "anthropic_model": os.environ.get("ANTHROPIC_MODEL", "claude-3.5-sonnet"),
            "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            "anthropic_base_url": os.environ.get("ANTHROPIC_BASE_URL", ""),
            "max_retries": int(os.environ.get("AI_MAX_RETRIES", "3")),
            "retry_delay": int(os.environ.get("AI_RETRY_DELAY", "60")),
        }

    def _initialize_providers(self) -> List[BaseProvider]:
        """Initialize available providers in priority order."""
        providers = []

        # Determine priority order
        preferred = self.config["preferred_provider"].lower()

        # Provider configurations
        provider_configs = [
            ("anthropic", AnthropicProvider, {"model": self.config["anthropic_model"], "base_url": self.config.get("anthropic_base_url")}),
            ("groq", GroqProvider, {"model": self.config["groq_model"]}),
            ("gemini", GeminiProvider, {"model": self.config["gemini_model"]}),
            ("together", TogetherProvider, {"model": self.config["together_model"]}),
            ("ollama", OllamaProvider, {"model": self.config["ollama_model"]}),
        ]

        # If auto, try to use preferred order based on reliability
        if preferred == "auto":
            # Try Groq first, then Anthropic, Gemini, Together, then Ollama
            #  (local, last fallback) 
            provider_configs = [
                ("anthropic", AnthropicProvider, {"model": self.config["anthropic_model"], "base_url": self.config.get("anthropic_base_url")}),
                ("groq", GroqProvider, {"model": self.config["groq_model"]}),
                ("gemini", GeminiProvider, {"model": self.config["gemini_model"]}),
                ("together", TogetherProvider, {"model": self.config["together_model"]}),
                ("ollama", OllamaProvider, {"model": self.config["ollama_model"]}),
            ]
        elif preferred in ["groq", "anthropic", "gemini", "together", "ollama"]:
            # Move preferred provider to front
            preferred_config = next((c for c in provider_configs if c[0] == preferred), None)
            if preferred_config:
                provider_configs.remove(preferred_config)
                provider_configs.insert(0, preferred_config)

        # Initialize providers
        for name, provider_class, config in provider_configs:
            try:
                self.console.print(f"[dim]→ Initializing {name} provider...[/dim]")
                provider = provider_class(**config)
                if provider.is_available():
                    providers.append(provider)
                    self.console.print(f"[green]✓ {name} provider available[/green]")
                else:
                    self.console.print(f"[yellow]⚠ {name} provider not available[/yellow]")
            except Exception as e:
                self.console.print(f"[yellow]⚠ {name} provider: {e}[/yellow]")

        return providers

    def _print_status(self):
        """Print provider status."""
        self.console.print()
        self.console.print(
            f"[cyan]🤖 Multi-Provider AI System[/cyan]"
        )
        self.console.print(f"[dim]Providers available: {len(self.providers)}[/dim]")

        for i, provider in enumerate(self.providers):
            info = provider.get_model_info()
            self.console.print(
                f"  [dim]{i+1}. {info['provider']} - {info['current_model']}[/dim]"
            )

        self.console.print()

    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """
        Generate text using available providers with automatic fallback.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters for generation

        Returns:
            Generated text content
        """
        # At minimum, try every provider once before giving up. The previous cap of 2
        # meant a 5-provider config (anthropic/groq/gemini/together/ollama) could exit
        # after only the first two failed, never reaching the local Ollama fallback.
        max_retries = max(self.config["max_retries"], len(self.providers))
        retry_delay = min(self.config["retry_delay"], 10)   # Max 10s delay

        for attempt in range(max_retries):
            # Try current provider
            provider = self.providers[self.current_provider_index]
            provider_name = provider.get_provider_name()

            try:
                self.console.print(f"[dim]Using {provider_name} provider...[/dim]")

                # Update health tracking
                self.provider_health[self.current_provider_index]["last_used"] = time.time()

                # Generate text (with timeout)
                response = provider.generate_text(messages, **kwargs)

                # Reset failure count on success
                self.provider_health[self.current_provider_index]["failures"] = 0

                self.console.print(f"[green]✓ {provider_name} succeeded[/green]")
                return response

            except (GroqRateLimitError, TogetherRateLimitError, AnthropicRateLimitError, GeminiRateLimitError) as e:
                # Handle rate limits
                self.console.print(f"[yellow]⚠ {provider_name} rate limit hit[/yellow]")
                self._handle_rate_limit(self.current_provider_index)

                # Try next provider immediately (no wait)
                if not self._rotate_provider():
                    # All providers exhausted, don't retry with long waits
                    raise RuntimeError(f"All providers exhausted - tried: {provider_name}")

            except Exception as e:
                # Handle other errors
                self.console.print(f"[red]✗ {provider_name} error: {e}[/red]")
                self.provider_health[self.current_provider_index]["failures"] += 1

                # Rotate to next provider immediately
                if not self._rotate_provider():
                    raise RuntimeError(f"All providers failed: {e}")

    def _rotate_provider(self) -> bool:
        """
        Rotate to next available provider.

        Returns:
            True if rotated successfully, False if no more providers
        """
        original_index = self.current_provider_index
        attempts = 0

        while attempts < len(self.providers):
            self.current_provider_index = (self.current_provider_index + 1) % len(self.providers)

            # Skip providers with too many failures
            failures = self.provider_health[self.current_provider_index]["failures"]
            if failures >= 3:
                attempts += 1
                continue

            if self.current_provider_index != original_index:
                provider = self.providers[self.current_provider_index]
                self.console.print(
                    f"[cyan]↻ Rotated to {provider.get_provider_name()} provider[/cyan]"
                )
                return True

            attempts += 1

        return False

    def _handle_rate_limit(self, provider_index: int):
        """Handle rate limit for a provider."""
        self.provider_health[provider_index]["failures"] += 1
        # Optionally add cooldown for this provider

    def _countdown(self, seconds: int):
        """Display countdown timer."""
        for i in range(seconds, 0, -5):
            self.console.print(f"[dim]{i}s remaining...[/dim]", end="\r")
            time.sleep(min(5, i))
        self.console.print()  # Clear the countdown line

    def get_current_provider(self) -> BaseProvider:
        """Get the current active provider."""
        return self.providers[self.current_provider_index]

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        return {
            "total_providers": len(self.providers),
            "current_provider": self.providers[self.current_provider_index].get_provider_name(),
            "provider_health": self.provider_health,
            "providers": [
                {
                    "name": p.get_provider_name(),
                    "model": p.get_model_info()["current_model"],
                    "is_available": p.is_available(),
                }
                for p in self.providers
            ]
        }