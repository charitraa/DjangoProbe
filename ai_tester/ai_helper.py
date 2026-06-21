import os
import re
from pathlib import Path
from rich.console import Console
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
console = Console()

# Import the new multi-provider system
from .providers.manager import ProviderManager


class AIHelper:
    """
    AI API client with multi-provider support.

    NVIDIA NIM is always first priority; groq/gemini/anthropic/together are
    used as fallbacks when their API key is configured in the environment.

    Usage:
        helper = AIHelper(repo_path)
        response = helper.client.generate_text(messages)
    """

    MAX_TOKENS = 8096

    def __init__(self, repo_path: str, analysis=None):
      self.repo_path = Path(repo_path)
      self.analysis  = analysis

      # Initialize the multi-provider manager
      try:
          self.provider_manager = ProviderManager(repo_path, analysis)
          # Set client to manager for backward compatibility
          self.client = self.provider_manager
          self.MODEL = self.provider_manager.get_current_provider().get_model_info()["current_model"]
      except Exception as e:
          console.print(f"[red]✗ Failed to initialize AI providers: {e}[/red]")
          raise SystemExit(1)

      # Parse installed apps (existing functionality)
      self.installed_apps = self._parse_installed_apps()
      console.print(
          f"  [dim]Found {len(self.installed_apps)} "
          f"project app(s) in INSTALLED_APPS[/dim]"
      )


    #  INSTALLED_APPS PARSER
    def _parse_installed_apps(self) -> list[dict]:
        """Read INSTALLED_APPS from settings.py."""

        settings_file = self._find_settings()
        if not settings_file:
            console.print("[yellow]⚠ Could not find settings.py[/yellow]")
            return []

        try:
            content = settings_file.read_text(errors="ignore")
        except Exception:
            return []

        match = re.search(
            r"INSTALLED_APPS\s*=\s*\[([^\]]*)\]",
            content, re.DOTALL,
        )
        if not match:
            return []

        raw_apps = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))

        skip_prefixes = {
            "django.", "rest_framework", "corsheaders",
            "django_filters", "allauth", "channels",
            "celery", "drf_", "debug_toolbar",
        }

        project_apps = []
        for app_module in raw_apps:
            if any(app_module.startswith(p) for p in skip_prefixes):
                continue

            app_dir  = self._resolve_app_dir(app_module)
            app_name = app_module.split(".")[-1]

            project_apps.append({
                "module":   app_module,
                "app_name": app_name,
                "app_dir":  app_dir,
            })

            status = "✓" if app_dir else "⚠"
            color  = "green" if app_dir else "yellow"
            console.print(
                f"  [{color}]{status}[/{color}] [dim]{app_module}[/dim]"
                + (
                    f" → {app_dir.relative_to(self.repo_path)}"
                    if app_dir else
                    " → [yellow]not found[/yellow]"
                )
            )

        return project_apps

    def _resolve_app_dir(self, app_module: str) -> Path | None:
        direct = self.repo_path / Path(app_module.replace(".", "/"))
        if direct.exists() and direct.is_dir():
            return direct

        last = app_module.split(".")[-1]
        for candidate in self.repo_path.rglob(last):
            if (
                candidate.is_dir()
                and (candidate / "models.py").exists()
                and not self._should_skip(candidate)
            ):
                return candidate
        return None

    def get_app_dir(self, app_name: str) -> Path | None:
        for app in self.installed_apps:
            if app["app_name"] == app_name:
                return app["app_dir"]
        return None

    #  HELPER METHODS FOR SETTINGS
    def _find_settings(self) -> Path | None:
        for candidate in self.repo_path.rglob("settings.py"):
            if not self._should_skip(candidate):
                return candidate
        return None

    def _should_skip(self, path: Path) -> bool:
        skip = {"venv", "env", "site-packages", "__pycache__", ".git"}
        return any(p in path.parts for p in skip)

    def call_with_retry(self, **kwargs) -> any:
        """
        Call AI API with retry logic using multi-provider system.

        Handles:
        - Rate limit errors
        - Provider rotation
        - Automatic fallback
        - Waiting between retries

        Returns:
            The API response or None if all retries exhausted
        """
        try:
            # Extract messages and parameters
            messages = kwargs.get("messages", [])
            max_tokens = kwargs.get("max_tokens", self.MAX_TOKENS)
            temperature = kwargs.get("temperature", 0.7)
            model = kwargs.get("model", self.MODEL)

            # Use the provider manager to generate text
            content = self.provider_manager.generate_text(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            # Return a mock response object for backward compatibility
            class MockResponse:
                def __init__(self, content):
                    self.choices = [MockChoice(content)]

            class MockChoice:
                def __init__(self, content):
                    self.message = MockMessage(content)

            class MockMessage:
                def __init__(self, content):
                    self.content = content

            return MockResponse(content)

        except Exception as e:
            console.print(f"  [red]✗ All providers failed: {e}[/red]")
            return None