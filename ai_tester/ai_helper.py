import os
import re
import time
from pathlib import Path
from openai import OpenAI
from rich.console import Console
from dotenv import load_dotenv

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
    
    #  PUBLIC
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

    #  CONTEXT COLLECTOR
    def _collect_context(self, app_name: str) -> dict[str, str]:
        """
        Dynamically read ALL relevant .py files from the app.
        Skip: migrations, tests, admin, apps, __init__
        """
        context: dict[str, str] = {}

        app_dir = self.get_app_dir(app_name)
        if not app_dir:
            console.print(
                f"  [yellow]⚠ App dir not found:[/yellow] {app_name}"
            )
            return context

        # Files to SKIP — not useful for test generation
        skip_files = {
            "__init__.py",
            "admin.py",
            "apps.py",
            "tests.py",
            "migrations",
        }

        # Priority files — read these first (most important)
        priority_files = [
            "models.py",
            "serializers.py",
            "views.py",
            "urls.py",
        ]

        # Secondary files — read if they exist
        secondary_files = [
            "services.py",
            "repository.py",
            "permissions.py",
            "filters.py",
            "utils.py",
            "signals.py",
            "forms.py",
            "tasks.py",
        ]

        def read_file(filepath: Path, label: str, max_chars: int) -> None:
            if filepath.exists():
                content = filepath.read_text(errors="ignore")
                context[label] = self._truncate(content, max_chars=max_chars)
                console.print(
                    f"    [dim]Read:[/dim] {app_name}/{label} "
                    f"[dim]({len(content)} chars)[/dim]"
                )

        # Read priority files with more tokens
        for fname in priority_files:
            read_file(app_dir / fname, fname, max_chars=4000)

        # Read secondary files with fewer tokens
        for fname in secondary_files:
            read_file(app_dir / fname, fname, max_chars=2000)

        # Catch any OTHER .py files not in our list
        known = set(priority_files + secondary_files + list(skip_files))
        for py_file in sorted(app_dir.glob("*.py")):
            if py_file.name not in known:
                read_file(py_file, py_file.name, max_chars=1000)
                console.print(
                    f"    [dim]Found extra file:[/dim] {py_file.name}"
                )

        # Read auth app context (login endpoint)
        auth_dir = self._find_auth_app()
        if auth_dir and auth_dir != app_dir:
            auth_app_name = auth_dir.name
            console.print(
                f"    [dim]Reading auth app:[/dim] {auth_app_name}/"
            )
            for fname in ["models.py", "serializers.py", "views.py", "urls.py"]:
                fp = auth_dir / fname
                if fp.exists():
                    content = fp.read_text(errors="ignore")
                    context[f"auth_{fname}"] = self._truncate(
                        content, max_chars=2000
                    )
                    console.print(
                        f"    [dim]Read:[/dim] {auth_app_name}/{fname} "
                        f"[dim](auth context)[/dim]"
                    )

        return context

    #  PROMPTS
    def _system_prompt(self) -> str:
        return (
            "You are an expert Django and DRF test engineer. "
            "You write clean, realistic, well-documented Django TestCase code. "
            "Return ONLY valid Python code — no markdown fences, "
            "no explanation, no preamble. "
            "Code must be directly writable to a .py file and executable."
        )
    
    # Add this method to AIHelper class
    def _find_root_urls(self) -> Path | None:
        """Find root urls.py — needed to detect login URL prefix."""
        settings_file = self._find_settings()
        if settings_file:
            try:
                content = settings_file.read_text(errors="ignore")
                match   = re.search(
                    r'ROOT_URLCONF\s*=\s*["\']([^"\']+)["\']', content
                )
                if match:
                    url_path = self.repo_path / Path(
                        match.group(1).replace(".", "/") + ".py"
                    )
                    if url_path.exists():
                        return url_path
            except Exception:
                pass

        # Fallback — find urls.py with most include() calls
        best_candidate = None
        best_score     = 0

        for candidate in sorted(self.repo_path.rglob("urls.py")):
            if self._should_skip(candidate):
                continue
            try:
                content = candidate.read_text(errors="ignore")
            except Exception:
                continue
            if "urlpatterns" not in content:
                continue
            score = content.count("include(")
            if score > best_score:
                best_score     = score
                best_candidate = candidate

        return best_candidate

    def _build_prompt(self, app_name, endpoints, context):

        if self.analysis:
            login_url     = self.analysis.login_url
            auth_module   = self.analysis.auth_module
            auth_app_name = self.analysis.auth_app_name
            safe_fields   = self.analysis.safe_user_fields
        else:
            # fallback if no analysis
            auth_dir      = self._find_auth_app()
            login_url     = self._find_login_url(auth_dir)
            auth_module   = "apps.user"
            auth_app_name = "user"
            safe_fields   = ["email", "full_name"]

        app_module = next(
        (app["module"] for app in self.installed_apps
         if app["app_name"] == app_name),
        f"apps.{app_name}"  # fallback
        )
        # Build safe create_user example from safe_fields
        safe_create = "\n        ".join([
            f'{f} = "test_{f}@example.com",' if "email" in f
            else f'{f} = "testpass123",' if "password" in f
            else f'{f} = "Test User",' if "name" in f
            else f'{f} = "test_value",'
            for f in safe_fields[:4]  # max 4 fields
        ])

        # Build FK setup code
        fk_imports = ""
        fk_creates = ""
        fk_in_create_user = ""

        if self.analysis and self.analysis.user_fk_fields:
            for fk in self.analysis.user_fk_fields:
                field = fk["field"]
                model = fk["model"]
                module = fk["module"]
                kwargs = ", ".join(f'{k}="{v}"' for k, v in fk["kwargs"].items())
                fk_imports += f"from {module}.models import {model}\n"
                fk_creates += f"        self.{field} = {model}.objects.create({kwargs})\n"
                fk_in_create_user += f"                {field}=self.{field},\n"

        # Build M2M setup code
        m2m_setup = ""
        if self.analysis and self.analysis.user_m2m_fields:
            for m2m in self.analysis.user_m2m_fields:
                m2m_setup += f"        # self.user.{m2m}.set([])  ← set after creation if needed\n"

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
        
        ## CRITICAL — Exact import paths for THIS project:
        - This app module path: {app_module}
        - Import models like:      from {app_module}.models import ModelName
        - Import from user app:    from apps.user.models import User
        - NEVER use relative imports (no from .models import ...)
        - NEVER import serializers — use plain dicts for POST data
        - NEVER use status.HTTP_xxx — use plain integers: 200, 201, 400, 401
        
        ```python
        # CORRECT imports:
        from django.test import TestCase, Client
        import json
        from {app_module}.models import <ModelName>      # models from THIS app
        from {auth_module}.models import User            # User model for auth

        # FORBIDDEN — never use these:
        from .models import ...          # relative imports
        from .serializers import ...     # relative imports
        from gallery.models import ...   # incomplete path
        from user.models import ...      # incomplete path
        from rest_framework import status  # use plain numbers instead
        from {app_module}.serializers import ...  # never import serializers
        from {app_module}.services import ...     # never import services
        ```
        ## Auth setup — login URL is: {login_url}
        ## ADMIN USER SETUP — use ONLY these safe fields:
        ## Safe fields detected from User model: {', '.join(safe_fields)}
        ## ManyToMany fields are excluded automatically
        
                ## ADMIN USER SETUP:
        ```python
        from django.test import TestCase, Client
        import json
        from {auth_module}.models import User
        {fk_imports}

        class AppTests(TestCase):
            def setUp(self):
                self.client = Client()
                {fk_creates}
                self.user = User.objects.create_user(
                    {safe_create}
                    {fk_in_create_user}
                    is_staff=True,
                    is_superuser=True,
                )
                {m2m_setup}
                response = self.client.post(
                    "{login_url}",
                    data=json.dumps({{
                        "email": "test@example.com",
                        "password": "testpass123"
                    }}),
                    content_type="application/json"
                )
                token = response.json().get("data", {{}}).get("access", "")
                self.auth_headers = {{"HTTP_AUTHORIZATION": f"Bearer {{token}}"}}
        ```
        ## RULES:
        - FK fields need related object created BEFORE User
        - M2M fields set AFTER User creation with .set()
        - NEVER pass FK as string — always pass object!
        ## Endpoints to test:
        {chr(10).join(endpoint_lines)}

        ## Project context:
        - Auth app: {auth_app_name}
        - Login URL: {login_url}

        ## Source code — read ALL files before writing:
        {chr(10).join(context_sections)}

        ## READING GUIDE:

        1. READ models.py → find EXACT field names and types
        2. READ serializers.py → find REQUIRED fields for POST/PUT
        3. READ views.py → find permission_classes (auth needed?)
        4. READ urls.py → find exact URL patterns and path params
        5. READ services/repository → understand what data is processed
        6. READ auth_models.py → find EXACT User model fields for setUp
        7. READ auth_urls.py → find the login endpoint URL

        ## TEST RULES:
        - Use ONLY field names visible in the source code above
        - Use ONLY model classes visible in the source code above
        - No relative imports
        - No APITestCase — use TestCase only
        - No status.HTTP_xxx — use 200, 201, 400, 401, 403, 404, 405
        - For logout: use assertIn([200, 205]) not assertEqual(200)
        - Add msg=f"Got {{response.status_code}}: {{response.content}}" to all assertions

        Return ONLY Python code. No markdown. No explanation.
        """

    #  HELPERS
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
    
    def _find_auth_app(self) -> Path | None:
        """
        Find auth app by reading AUTH_USER_MODEL from settings.py
        
        AUTH_USER_MODEL = 'apps.user.User'  → apps/user/
        AUTH_USER_MODEL = 'accounts.User'   → accounts/
        AUTH_USER_MODEL = 'core.User'       → core/
        """
        settings_file = self._find_settings()
        if not settings_file:
            return None

        content = settings_file.read_text(errors="ignore")

        # Find AUTH_USER_MODEL = 'app.Model'
        match = re.search(
            r'AUTH_USER_MODEL\s*=\s*["\']([^"\']+)["\']',
            content
        )
        if not match:
            return None

        # 'apps.user.User' → 'apps.user' → apps/user/
        auth_model = match.group(1)          # e.g. "apps.user.User"
        parts      = auth_model.split(".")   # ["apps", "user", "User"]
        app_module = ".".join(parts[:-1])    # "apps.user"

        return self._resolve_app_dir(app_module)
    
    def _find_login_url(self, auth_dir: Path | None) -> str:
        """
        Find login URL by reading auth app urls.py
        Returns something like /api/user/login/
        """
        if not auth_dir:
            return "/api/user/login/"

        urls_file = auth_dir / "urls.py"
        if not urls_file.exists():
            return "/api/user/login/"

        content = urls_file.read_text(errors="ignore")

        # Look for login pattern
        match = re.search(
            r'path\(["\']([^"\']*login[^"\']*)["\']',
            content,
            re.IGNORECASE
        )

        if match:
            # Get the prefix from root urls.py too
            prefix = self._find_app_url_prefix(auth_dir.name)
            return f"/{prefix}{match.group(1)}".replace("//", "/")

        return "/api/user/login/"

    def _find_app_url_prefix(self, app_name: str) -> str:
        """Find URL prefix for an app from root urls.py"""
        root_urls = self._find_root_urls()
        if not root_urls:
            return ""

        content = root_urls.read_text(errors="ignore")

        # path('api/user/', include('apps.user.urls'))
        match = re.search(
            rf'path\(["\']([^"\']+)["\'],\s*include\(["\'][^"\']*{app_name}[^"\']*["\']',
            content
        )
        if match:
            return match.group(1)
        return ""