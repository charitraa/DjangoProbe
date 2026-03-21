import os
import re
import time
from pathlib import Path

from openai import OpenAI
from rich.console import Console
from dotenv import load_dotenv

from ai_tester.models import EndpointInfo

load_dotenv()
console = Console()


class AIHelper:
    """
    Communicates with Groq API to generate intelligent test cases.

    Groq free tier:
      - 14,400 requests per day
      - 30 requests per minute
      - Much faster than OpenRouter free models

    Usage:
        helper  = AIHelper(repo_path)
        content = helper.generate_tests(app_name, endpoints)
    """

    # Best models on Groq for code generation
    MODEL = "llama-3.3-70b-versatile"

    FALLBACK_MODELS = [
        "llama-3.1-8b-instant",          # fast, still works
        "gemma2-9b-it",                  # Google model on Groq, works
    ]

    MAX_TOKENS = 8096

    def __init__(self, repo_path: str):
      self.repo_path = Path(repo_path)

      # ── Load all 3 keys ───────────────────────
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
    # ─────────────────────────────────────────
    #  PUBLIC
    # ─────────────────────────────────────────

    def generate_tests(self, app_name, endpoints):
        console.print(
            f"  [dim]→ Groq generating tests for:[/dim] "
            f"[cyan]{app_name}[/cyan]"
        )

        context  = self._collect_context(app_name)
        prompt   = self._build_prompt(app_name, endpoints, context)
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user",   "content": prompt},
        ]

        for model in [self.MODEL] + self.FALLBACK_MODELS:
            for attempt in range(len(self.api_keys) * 2):  # enough attempts for all keys
                try:
                    with console.status(
                        f"  [dim]Calling {model} "
                        f"[key {self.current_key_index + 1}]...[/dim]",
                        spinner="dots"
                    ):
                        response = self.client.chat.completions.create(
                            model      = model,
                            max_tokens = self.MAX_TOKENS,
                            messages   = messages,
                        )

                    content = response.choices[0].message.content
                    if content:
                        return content

                except Exception as e:
                    err = str(e).lower()

                    if "decommissioned" in err or "model_decommissioned" in err:
                        console.print(
                            f"  [yellow]⚠ Decommissioned:[/yellow] {model} — skipping"
                        )
                        break  # next model

                    elif "429" in err or "rate limit" in err:
                        console.print(
                            f"  [yellow]⚠ Rate limit on key "
                            f"{self.current_key_index + 1}[/yellow]"
                        )
                        # Try rotating key first
                        if self._rotate_key():
                            continue  # retry with new key immediately
                        else:
                            # With this:
                            for remaining in range(60, 0, -1):
                                console.print(
                                    f"  [yellow]⚠ All keys rate limited — "
                                    f"retrying in {remaining}s...[/yellow]",
                                    end="\r"   # ← overwrite same line
                                )
                                time.sleep(1)
                            console.print(
                                "  [green]✓ Rate limit cleared — retrying...[/green]    "
                            )

                    else:
                        console.print(f"  [red]✗ Groq error:[/red] {e}")
                        break  # next model

        console.print("[red]✗ All models and keys failed.[/red]")
        return None
    # ─────────────────────────────────────────
    #  INSTALLED_APPS PARSER
    # ─────────────────────────────────────────

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

    # ─────────────────────────────────────────
    #  CONTEXT COLLECTOR
    # ─────────────────────────────────────────

    def _collect_context(self, app_name: str) -> dict[str, str]:
        context: dict[str, str] = {}
        files_to_read = [
            "models.py", "serializers.py",
            "views.py",  "urls.py",
            "permissions.py", "services.py",
        ]

        app_dir = self.get_app_dir(app_name)
        if not app_dir:
            console.print(
                f"  [yellow]⚠ App dir not found:[/yellow] {app_name}"
            )
            return context

        for filename in files_to_read:
            file_path = app_dir / filename
            if file_path.exists():
                content = file_path.read_text(errors="ignore")
                context[filename] = self._truncate(content, max_chars=3000)
                console.print(
                    f"    [dim]Read:[/dim] {app_name}/{filename} "
                    f"[dim]({len(content)} chars)[/dim]"
                )
        return context

    # ─────────────────────────────────────────
    #  PROMPTS
    # ─────────────────────────────────────────

    def _system_prompt(self) -> str:
        return (
            "You are an expert Django and DRF test engineer. "
            "You write clean, realistic, well-documented Django TestCase code. "
            "Return ONLY valid Python code — no markdown fences, "
            "no explanation, no preamble. "
            "Code must be directly writable to a .py file and executable."
        )

    def _build_prompt(
        self,
        app_name:  str,
        endpoints: list[EndpointInfo],
        context:   dict[str, str],
    ) -> str:

        endpoint_lines = [
            f"  - [{', '.join(ep.http_methods)}]  "
            f"{ep.url_pattern}  "
            f"view={ep.view_name}  "
            f"({'requires auth' if ep.requires_auth else 'public'})"
            for ep in endpoints
        ]

        context_sections = [
            f"### {fname}\n```python\n{code}\n```"
            for fname, code in context.items()
        ]

        return f"""
Generate a complete Django test file for the "{app_name}" app.

## Endpoints:
{chr(10).join(endpoint_lines)}

## Source code:
{chr(10).join(context_sections)}

## Requirements:
1. Header comment: app name + "Auto-generated by DjangoProbe"
2. Class: `{app_name.capitalize()}AppTests(TestCase)`
3. setUp: create test client, test data, auth token if needed
   Store token as: self.auth_headers = {{"HTTP_AUTHORIZATION": "Bearer <token>"}}
4. Per endpoint:
   a) Success test → 200/201 with real data from serializer
   b) Validation test → 400 for empty POST/PUT/PATCH body
   c) Auth test → 401 without token, 200/403 with token
   d) Wrong method → 405
5. Path params like /api/user/<str:user_id>/: create object in setUp, use real ID
6. Docstring per test method
7. self.assertEqual / self.assertIn with msg= arguments
8. All imports at top

Return ONLY Python code. No markdown. No explanation.
"""

    # ─────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────

    def _find_settings(self) -> Path | None:
        for candidate in self.repo_path.rglob("settings.py"):
            if not self._should_skip(candidate):
                return candidate
        return None

    def _should_skip(self, path: Path) -> bool:
        skip = {"venv", "env", "site-packages", "__pycache__", ".git"}
        return any(p in path.parts for p in skip)

    def _truncate(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n\n# ... (truncated)"