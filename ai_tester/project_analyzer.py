import re
import ast
from pathlib import Path

from rich.console import Console
from ai_tester.models import ProjectAnalysis

console = Console()


class ProjectAnalyzer:
    """
    Analyzes a Django project ONCE before test generation.

    Discovers:
      - Auth type (JWT / Session / Token)
      - Login URL
      - Auth app and module path
      - Safe User model fields (excludes ManyToMany)
      - Available roles

    Usage:
        analyzer = ProjectAnalyzer(repo_path)
        analysis = analyzer.analyze()
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    #  PUBLIC
    def analyze(self) -> ProjectAnalysis:
        auth_type = self._detect_auth_type()
        auth_dir = self._find_auth_app()
        auth_module = self._get_auth_module(auth_dir)
        auth_app_name = auth_dir.name if auth_dir else "user"
        login_url = self._find_login_url(auth_dir)
        safe_fields = self._get_safe_user_fields(auth_dir)
        fk_fields = self._get_user_fk_fields(auth_dir)
        m2m_fields = self._get_user_m2m_fields(auth_dir)
        roles = self._get_available_roles(auth_dir)

        console.print(f"  [dim]Auth type:[/dim]    [cyan]{auth_type}[/cyan]")
        console.print(f"  [dim]Auth app:[/dim]     [cyan]{auth_module}[/cyan]")
        console.print(f"  [dim]Login URL:[/dim]    [cyan]{login_url}[/cyan]")
        console.print(f"  [dim]Safe fields:[/dim]  [cyan]{', '.join(safe_fields)}[/cyan]")

        if fk_fields:
            fk_names = [f["field"] for f in fk_fields]
            console.print(
                f"  [dim]FK fields:[/dim]    [yellow]{', '.join(fk_names)}[/yellow]"
            )
        if m2m_fields:
            console.print(
                f"  [dim]M2M fields:[/dim]   [yellow]{', '.join(m2m_fields)}[/yellow]"
            )

        return ProjectAnalysis(
            auth_type=auth_type,
            login_url=login_url,
            auth_module=auth_module,
            auth_app_name=auth_app_name,
            safe_user_fields=safe_fields,
            roles=roles,
            user_fk_fields=fk_fields,
            user_m2m_fields=m2m_fields,
        )

    #  AUTH TYPE DETECTION
    def _detect_auth_type(self) -> str:
        """
        Detect auth type from settings.py and requirements.txt

        Checks for:
          - djangorestframework-simplejwt → JWT
          - rest_framework.authtoken      → Token
          - django session auth           → Session
        """
        # Check requirements.txt
        req_file = self.repo_path / "requirements.txt"
        if req_file.exists():
            content = req_file.read_text(errors="ignore").lower()
            if "simplejwt" in content or "djangorestframework-simplejwt" in content:
                return "JWT"
            if "authtoken" in content or "knox" in content:
                return "Token"

        # Check settings.py
        settings = self._find_settings()
        if settings:
            content = settings.read_text(errors="ignore")
            if "simplejwt" in content or "SimpleJWT" in content:
                return "JWT"
            if "rest_framework.authtoken" in content:
                return "Token"
            if "SessionAuthentication" in content:
                return "Session"

        # Check installed packages in venv
        venv_path = self.repo_path / ".probe_venv"
        if venv_path.exists():
            for p in venv_path.rglob("rest_framework_simplejwt*"):
                return "JWT"

        return "JWT"  # default assumption for DRF projects

    #  AUTH APP FINDER
    def _find_auth_app(self) -> Path | None:
        """Find auth app via AUTH_USER_MODEL in settings.py"""
        settings = self._find_settings()
        if not settings:
            return None

        content = settings.read_text(errors="ignore")
        match   = re.search(
            r'AUTH_USER_MODEL\s*=\s*["\']([^"\']+)["\']',
            content
        )
        if not match:
            return None

        # 'apps.user.User' → apps/user/
        auth_model = match.group(1)
        parts      = auth_model.split(".")
        app_module = ".".join(parts[:-1])

        return self._resolve_app_dir(app_module)

    def _get_auth_module(self, auth_dir: Path | None) -> str:
        """Get dotted module path for auth app."""
        if not auth_dir:
            return "apps.user"

        # Try to find it from settings INSTALLED_APPS
        settings = self._find_settings()
        if settings:
            content  = settings.read_text(errors="ignore")
            match    = re.search(
                r"INSTALLED_APPS\s*=\s*\[([^\]]*)\]",
                content, re.DOTALL
            )
            if match:
                apps = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
                for app in apps:
                    if app.endswith(auth_dir.name):
                        return app

        # Fallback — build from path
        try:
            rel = auth_dir.relative_to(self.repo_path)
            return str(rel).replace("/", ".")
        except Exception:
            return f"apps.{auth_dir.name}"

    #  LOGIN URL FINDER
    def _find_login_url(self, auth_dir: Path | None) -> str:
        """Find login URL from auth app urls.py + root urls.py prefix."""
        if not auth_dir:
            return "/api/user/login/"

        urls_file = auth_dir / "urls.py"
        if not urls_file.exists():
            return "/api/user/login/"

        content = urls_file.read_text(errors="ignore")
        match   = re.search(
            r'path\(["\']([^"\']*login[^"\']*)["\']',
            content, re.IGNORECASE
        )

        if match:
            local_path = match.group(1)
            prefix     = self._find_url_prefix(auth_dir.name)
            full       = f"/{prefix}{local_path}".replace("//", "/")
            return full

        return "/api/user/login/"

    def _find_url_prefix(self, app_name: str) -> str:
        """Find URL prefix for app from root urls.py."""
        root_urls = self._find_root_urls()
        if not root_urls:
            return ""

        content = root_urls.read_text(errors="ignore")
        match   = re.search(
            rf'path\(["\']([^"\']+)["\'],\s*include\(["\'][^"\']*{app_name}[^"\']*["\']',
            content
        )
        return match.group(1) if match else ""

    def _get_safe_user_fields(self, auth_dir: Path | None) -> list[str]:
        """Return ONLY simple safe fields — excludes FK and M2M."""
        safe, _, _ = self._analyze_user_model(auth_dir)
        return safe

    def _get_user_fk_fields(self, auth_dir: Path | None) -> list:
        """Return ForeignKey field info."""
        _, fk_fields, _ = self._analyze_user_model(auth_dir)
        return fk_fields

    def _get_user_m2m_fields(self, auth_dir: Path | None) -> list[str]:
        """Return ManyToMany field names."""
        _, _, m2m = self._analyze_user_model(auth_dir)
        return m2m

    def _analyze_user_model(self, auth_dir: Path | None) -> tuple:
        """
        Parse User model and classify all fields:
        Returns: (safe_fields, fk_fields, m2m_fields)

        safe_fields  = ["email", "full_name"]         ← pass directly to create_user
        fk_fields    = [{"field": "role",             ← ForeignKey, create first
                         "model": "Role",
                         "module": "apps.user.models"}]
        m2m_fields   = ["pages"]                      ← set after creation
        """
        if not auth_dir:
            return ["email", "full_name"], [], []

        models_file = auth_dir / "models.py"
        if not models_file.exists():
            return ["email", "full_name"], [], []

        try:
            source = models_file.read_text(errors="ignore")
            tree = ast.parse(source)
        except Exception:
            return ["email", "full_name"], [], []

        safe_fields = []
        fk_fields = []
        m2m_fields = []

        m2m_types = {"ManyToManyField"}
        fk_types = {"ForeignKey", "OneToOneField"}
        unsafe_types = m2m_types | fk_types | {"ManyToOneRel"}

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            bases = [ast.unparse(b) for b in node.bases]
            is_user = any(
                "User" in b or "AbstractUser" in b or "AbstractBaseUser" in b
                for b in bases
            ) or node.name == "User"

            if not is_user:
                continue

            for item in node.body:
                if not isinstance(item, ast.Assign):
                    continue

                for target in item.targets:
                    if not isinstance(target, ast.Name):
                        continue

                    field_name = target.id
                    if field_name.startswith("_"):
                        continue

                    if not isinstance(item.value, ast.Call):
                        continue

                    # Get field type
                    field_type = ""
                    if isinstance(item.value.func, ast.Name):
                        field_type = item.value.func.id
                    elif isinstance(item.value.func, ast.Attribute):
                        field_type = item.value.func.attr

                    if not field_type:
                        continue

                    if field_type in m2m_types:
                        # ManyToMany — set after creation
                        m2m_fields.append(field_name)

                    elif field_type in fk_types:
                        # ForeignKey — need to create related object first
                        related_model = self._get_fk_related_model(item.value)
                        create_kwargs = self._guess_create_kwargs(
                            related_model, source
                        )
                        fk_fields.append({
                            "field": field_name,
                            "model": related_model,
                            "module": self._get_auth_module(auth_dir),
                            "kwargs": create_kwargs,
                        })

                    elif "Field" in field_type:
                        # Regular safe field
                        safe_fields.append(field_name)

        # Add basic fields if missing
        for b in ["email", "full_name"]:
            if b not in safe_fields and re.search(rf'\b{b}\s*=', source):
                safe_fields.append(b)

        return safe_fields or ["email", "full_name"], fk_fields, m2m_fields

    def _get_fk_related_model(self, call_node: ast.Call) -> str:
        """Extract related model name from ForeignKey(RelatedModel, ...)"""
        if call_node.args:
            first = call_node.args[0]
            if isinstance(first, ast.Name):
                return first.id
            if isinstance(first, ast.Constant):
                # String reference like ForeignKey("Role", ...)
                val = str(first.value)
                return val.split(".")[-1]
        return "RelatedModel"

    def _guess_create_kwargs(self, model_name: str, source: str) -> dict:
        """
        Guess minimal kwargs to create the related model.
        Looks for the model class and finds its required fields.
        """
        # Simple heuristic — look for name, title fields
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == model_name:
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name):
                                    if target.id == "name":
                                        return {"name": "admin"}
                                    if target.id == "title":
                                        return {"title": "Test"}
        except Exception:
            pass
        return {"name": "admin"}  # safe default

    #  ROLES FINDER
    def _get_available_roles(self, auth_dir: Path | None) -> list[str]:
        """
        Find available roles from Role model if it exists.
        Returns list like: ['admin', 'teacher', 'student']
        """
        if not auth_dir:
            return []

        models_file = auth_dir / "models.py"
        if not models_file.exists():
            return []

        content = models_file.read_text(errors="ignore")

        # Look for choices like:
        # ROLE_CHOICES = [('admin', 'Admin'), ('teacher', 'Teacher')]
        match = re.search(
            r'ROLE_CHOICES\s*=\s*\[([^\]]+)\]',
            content, re.DOTALL
        )
        if match:
            return re.findall(r"['\"](\w+)['\"]", match.group(1))[::2]

        # Look for Role model with name field
        if "class Role" in content:
            return []  # dynamic roles in DB

        return []

    #  HELPERS
    def _find_settings(self) -> Path | None:
        for candidate in self.repo_path.rglob("settings.py"):
            if not self._should_skip(candidate):
                return candidate
        return None

    def _find_root_urls(self) -> Path | None:
        settings = self._find_settings()
        if settings:
            try:
                content = settings.read_text(errors="ignore")
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

        best, best_score = None, 0
        for candidate in sorted(self.repo_path.rglob("urls.py")):
            if self._should_skip(candidate):
                continue
            try:
                content = candidate.read_text(errors="ignore")
                score   = content.count("include(")
                if score > best_score:
                    best_score = score
                    best       = candidate
            except Exception:
                continue
        return best

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

    def _should_skip(self, path: Path) -> bool:
        skip = {"venv", "env", "site-packages", "__pycache__", ".git", ".probe_venv"}
        return any(p in path.parts for p in skip)