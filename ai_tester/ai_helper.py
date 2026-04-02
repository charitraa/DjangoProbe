import os
import re
from pathlib import Path
from openai import OpenAI
from rich.console import Console
from dotenv import load_dotenv

load_dotenv()
console = Console()


class AIHelper:
    """
    AI API client for Groq communication.

    Groq free tier:
      - 14,400 requests per day
      - 30 requests per minute
      - Much faster than OpenRouter free models

    Usage:
        helper = AIHelper(repo_path)
        response = helper.client.chat.completions.create(...)
    """

    # Best models on Groq for code generation
    MODEL = "llama-3.3-70b-versatile"

    FALLBACK_MODELS = [
        "llama-3.1-8b-instant",          # fast, still works
        "gemma2-9b-it",                  # Google model on Groq, works
    ]

    MAX_TOKENS = 8096

    def __init__(self, repo_path: str, analysis=None):
      self.repo_path = Path(repo_path)
      self.analysis  = analysis
      # Load all 3 keys
      self.api_keys = []
      for i in range(1, 4):
          key = os.environ.get(f"GROQ_API_KEY_{i}")
          if key:
              self.api_keys.append(key)

      # Fallback to single key if user has only one
      if not self.api_keys:
          single = os.environ.get("GROQ_API_KEY")
          if single:
              self.api_keys.append(single)

      if not self.api_keys:
          console.print(
              "[red]✗ No Groq API keys found![/red]\n"
              "  Add to .env:\n"
              "  GROQ_API_KEY_1='gsk_...'\n"
              "  GROQ_API_KEY_2='gsk_...'\n"
              "  GROQ_API_KEY_3='gsk_...'"
          )
          raise SystemExit(1)

      self.current_key_index = 0  # start with key 1

      # Build client with first key
      self.client = self._build_client(self.api_keys[0])

      console.print(
          f"  [dim]AI Provider:[/dim] [cyan]Groq[/cyan] "
          f"[dim]({self.MODEL}) — {len(self.api_keys)} key(s) loaded[/dim]"
      )

      self.installed_apps = self._parse_installed_apps()
      console.print(
          f"  [dim]Found {len(self.installed_apps)} "
          f"project app(s) in INSTALLED_APPS[/dim]"
      )

    def _build_client(self, api_key: str) -> OpenAI:
      """Build OpenAI client with given key."""
      return OpenAI(
          api_key  = api_key,
          base_url = "https://api.groq.com/openai/v1",
      )

    def _rotate_key(self) -> bool:
        """
        Rotate to next API key.
        Returns True if rotated, False if no more keys.
        """
        next_index = self.current_key_index + 1

        if next_index >= len(self.api_keys):
            return False  # no more keys

        self.current_key_index = next_index
        self.client = self._build_client(self.api_keys[next_index])

        console.print(
            f"  [cyan]↻ Rotated to key {next_index + 1}/{len(self.api_keys)}[/cyan]"
        )
        return True

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