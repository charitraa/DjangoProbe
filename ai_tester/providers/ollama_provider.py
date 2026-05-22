"""
Ollama AI provider implementation.
Completely free, runs locally on your machine.
"""
import subprocess
import json
from typing import List, Optional
from pathlib import Path
from rich.console import Console

from .base import BaseProvider


class OllamaProvider(BaseProvider):
    """
    Ollama AI provider for local model inference.

    Completely free and runs locally.
    Requires Ollama to be installed and running.

    Installation:
        curl -fsSL https://ollama.ai/install.sh | sh

    Usage:
        ollama run llama3.2
        ollama run mistral

    Models:
    - llama3.2: Meta's Llama 3.2 (3B, 7B, 70B)
    - mistral: Mistral 7B
    - qwen2.5: Alibaba's Qwen 2.5
    - codellama: Code-optimized Llama
    """

    DEFAULT_MODEL = "llama3.2"
    BASE_URL = "http://localhost:11434"

    # Recommended models for code generation
    MODELS = {
        "llama3.2": {
            "quality": "high",
            "speed": "medium",
            "size": "3B/7B/70B",
            "description": "Meta's Llama 3.2, excellent for code"
        },
        "mistral": {
            "quality": "high",
            "speed": "fast",
            "size": "7B",
            "description": "Mistral 7B, good performance"
        },
        "qwen2.5": {
            "quality": "high",
            "speed": "fast",
            "size": "7B/14B",
            "description": "Alibaba's Qwen, great for code"
        },
        "codellama": {
            "quality": "high",
            "speed": "medium",
            "size": "7B/13B/34B",
            "description": "Code-optimized Llama"
        }
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, model=model, **kwargs)

        # Ollama doesn't need API key, but we accept for interface consistency
        self.api_key = api_key  # Not used for Ollama

        self.model = model or self.DEFAULT_MODEL
        self.base_url = kwargs.get("base_url", self.BASE_URL)
        self.console = Console()

        # Check if Ollama is available
        if not self._is_ollama_running():
            raise RuntimeError(
                "Ollama is not running. Start it with:\n"
                "  ollama serve\n"
                "In a separate terminal, or enable it to start automatically."
            )

        # Check if model is available
        if not self._is_model_available(self.model):
            self.console.print(f"[yellow]⚠ Model '{self.model}' not found, using qwen3.5 instead.[/yellow]")
            self.model = "qwen3.5"  # Fallback to an available model

    def generate_text(self, messages: List[dict], **kwargs) -> str:
        """
        Generate text using Ollama API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Generated text content
        """
        import requests

        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}

        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            role_map = {
                "system": "system",
                "user": "user",
                "assistant": "assistant"
            }
            ollama_messages.append({
                "role": role_map.get(msg.get("role", "user"), "user"),
                "content": msg.get("content", "")
            })

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
            }
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama request timed out after 120s")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API error: {e}")

    def get_model_info(self) -> dict:
        """Get information about Ollama models."""
        return {
            "provider": "Ollama",
            "current_model": self.model,
            "available_models": self._get_local_models(),
            "base_url": self.base_url,
            "is_local": True,
            "is_free": True
        }

    def is_available(self) -> bool:
        """Check if Ollama is accessible."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def _is_ollama_installed(self) -> bool:
        """Check if Ollama is installed."""
        try:
            subprocess.run(
                ["ollama", "--version"],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _is_ollama_running(self) -> bool:
        """Check if Ollama server is running."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def _is_model_available(self, model: str) -> bool:
        """Check if a specific model is downloaded."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(model in m.get("name", "") for m in models)
            return False
        except Exception:
            return False

    def _get_local_models(self) -> dict:
        """Get list of downloaded models."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return {
                    m.get("name", "").split(":")[0]: {
                        "size": m.get("size", "unknown"),
                        "modified": m.get("modified_at", "unknown")
                    }
                    for m in models
                }
            return {}
        except Exception:
            return {}