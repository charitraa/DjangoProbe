import ast
import re
from pathlib import Path
from rich.console import Console
from ai_tester.models import EndpointInfo

console = Console()

class EndpointScanner:
    """
    Scans a Django project and discovers all API endpoints.

    Usage:
        scanner   = EndpointScanner(repo_path)
        endpoints = scanner.scan()
    """

    SKIP_DIRS = {"venv", "env", "site-packages", "__pycache__", ".git"}

    AUTH_CLASSES = {
        "IsAuthenticated",
        "IsAdminUser",
        "IsAuthenticatedOrReadOnly",
        "DjangoModelPermissions",
    }
    
    SKIP_URL_PREFIXES = {
    "admin/",
    "admin",
    "__debug__/",
    "silk/",
    "swagger/",
    "redoc/",
    "api-auth/",
    "api/schema/",
}


    def __init__(self, repo_path: str):
        self.repo_path : Path             = Path(repo_path)
        self.endpoints : list[EndpointInfo] = []
        self.visited   : set[str]         = set()

    #  PUBLIC — main entry
    def scan(self) -> list[EndpointInfo]:
        """Scan all urls.py files and return discovered endpoints."""

        root_urls = self._find_root_urls()

        if not root_urls:
            console.print("[red]✗ Could not find root urls.py[/red]")
            return []

        console.print(
            f"  [dim]Root URLs:[/dim] "
            f"{root_urls.relative_to(self.repo_path)}"
        )

        self._parse_urls_file(urls_file=root_urls, prefix="")
        self._check_duplicates()

        return self.endpoints

    #  FIND ROOT urls.py
    def _find_root_urls(self) -> Path | None:
        """Find the root urls.py via ROOT_URLCONF or heuristic."""

        # Strategy 1 — read ROOT_URLCONF from settings.py
        settings_file = self._find_settings()
        if settings_file:
            root_urlconf = self._extract_root_urlconf(settings_file)
            if root_urlconf:
                console.print(f"  [dim]ROOT_URLCONF:[/dim] {root_urlconf}")
                url_path = self.repo_path / Path(
                    root_urlconf.replace(".", "/") + ".py"
                )
                if url_path.exists():
                    return url_path

        # Strategy 2 — find urls.py with most include() calls (likely root)
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

    def _find_settings(self) -> Path | None:
        """Find settings.py in the repo."""
        for candidate in self.repo_path.rglob("settings.py"):
            if not self._should_skip(candidate):
                return candidate
        return None
    def _get_project_apps(self) -> list[str]:
        """
        Read INSTALLED_APPS from settings.py.
        Returns list of app module strings.

        Example:
            ["apps.user", "apps.gallery", "blog"]
        """
        settings_file = self._find_settings()
        if not settings_file:
            return []

        try:
            content = settings_file.read_text(errors="ignore")
        except Exception:
            return []

        match = re.search(
            r"INSTALLED_APPS\s*=\s*\[([^\]]*)\]",
            content,
            re.DOTALL,
        )
        if not match:
            return []

        raw_apps = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))

        skip_prefixes = {
            "django.", "rest_framework", "corsheaders",
            "django_filters", "allauth", "channels",
            "celery", "drf_", "debug_toolbar",
        }

        return [
            app for app in raw_apps
            if not any(app.startswith(p) for p in skip_prefixes)
        ]
    def _extract_root_urlconf(self, settings_file: Path) -> str | None:
        """Extract ROOT_URLCONF value from settings.py."""
        try:
            content = settings_file.read_text(errors="ignore")
            match   = re.search(
                r'ROOT_URLCONF\s*=\s*["\']([^"\']+)["\']', content
            )
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    #  PARSE urls.py — Recursive
    def _parse_urls_file(self, urls_file: Path, prefix: str) -> None:
        """
        Parse a urls.py using AST.
        Recursively follows include() calls.
        """

        real_path = str(urls_file.resolve())
        if real_path in self.visited:
            return
        self.visited.add(real_path)

        if not urls_file.exists():
            return

        try:
            source = urls_file.read_text(errors="ignore")
            tree   = ast.parse(source)
        except SyntaxError as e:
            console.print(
                f"  [yellow]⚠ Skipping {urls_file.name} "
                f"(syntax error): {e}[/yellow]"
            )
            return

        app_name   = urls_file.parent.name
        router_map = self._extract_router_registrations(tree, urls_file)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue

            targets = [
                t for t in node.targets
                if self._get_name(t) == "urlpatterns"
            ]
            if not targets:
                continue

            # urlpatterns = router.urls
            if (
                isinstance(node.value, ast.Attribute)
                and node.value.attr == "urls"
            ):
                for ep_list in router_map.values():
                    for ep in ep_list:
                        ep.url_pattern = prefix.rstrip("/") + ep.url_pattern
                        self.endpoints.append(ep)
                continue

            # urlpatterns = [...] or [...] + router.urls
            items = self._extract_list_items(node.value)
            for item in items:
                self._process_url_item(
                    item, prefix, app_name, urls_file, router_map
                )

    def _process_url_item(
        self,
        item,
        prefix:    str,
        app_name:  str,
        urls_file: Path,
        router_map: dict,
    ) -> None:
        """Process one entry inside urlpatterns list."""

        if not isinstance(item, ast.Call):
            return

        func_name = self._get_call_name(item)

        # include()
        if func_name in ("include", "re_path") and self._has_include(item):
            self._follow_include(item, prefix)
            return

        # path() / re_path() / url()
        if func_name in ("path", "re_path", "url"):
            pattern  = self._extract_first_arg(item) or ""
            full_url = "/" + (prefix + pattern).strip("/")
        #Skip built-in Django routes
            if any(
                pattern.startswith(skip)
                for skip in self.SKIP_URL_PREFIXES
            ):
                console.print(
                    f"  [dim]↷ Skipping built-in:[/dim] {full_url}"
                )
                return
            # Second arg is include()
            second = self._get_nth_arg(item, 1)
            if (
                second
                and isinstance(second, ast.Call)
                and self._get_call_name(second) == "include"
            ):
                self._follow_include(second, prefix + pattern)
                return

            # Normal endpoint
            view_name = self._extract_view_name(item)
            if view_name:
                methods, requires_auth = self._resolve_view_info(
                    view_name, urls_file
                )
                self.endpoints.append(EndpointInfo(
                    url_pattern   = full_url,
                    http_methods  = methods,
                    view_name     = view_name,
                    requires_auth = requires_auth,
                    app_name      = app_name,
                ))

    def _follow_include(self, node: ast.Call, prefix: str) -> None:
        """Resolve an include() and recurse into that urls.py."""
        include_path = self._extract_include_path(node)
        if include_path:
            sub_file = self._resolve_module_to_file(include_path)
            if sub_file:
                self._parse_urls_file(sub_file, prefix)

    #  DRF ROUTER DETECTION
    def _extract_router_registrations(
        self,
        tree:      ast.Module,
        urls_file: Path,
    ) -> dict[str, list[EndpointInfo]]:
        """Find router.register() calls and expand to CRUD endpoints."""

        router_map: dict[str, list[EndpointInfo]] = {}
        app_name = urls_file.parent.name

        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr):
                continue
            if not isinstance(node.value, ast.Call):
                continue

            call = node.value
            if not (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "register"
            ):
                continue

            if len(call.args) < 2:
                continue

            prefix_arg  = call.args[0]
            viewset_arg = call.args[1]

            if not isinstance(prefix_arg, ast.Constant):
                continue

            url_prefix   = str(prefix_arg.value)
            viewset_name = self._get_name(viewset_arg) or "UnknownViewSet"
            _, requires_auth = self._resolve_view_info(viewset_name, urls_file)

            router_map[url_prefix] = [
                EndpointInfo(
                    f"/{url_prefix}/",
                    ["GET", "POST"],
                    viewset_name,
                    requires_auth,
                    app_name,
                ),
                EndpointInfo(
                    f"/{url_prefix}/{{id}}/",
                    ["GET", "PUT", "PATCH", "DELETE"],
                    viewset_name,
                    requires_auth,
                    app_name,
                ),
            ]

        return router_map


    #  VIEW INFO RESOLUTION
    def _resolve_view_info(
        self,
        view_name: str,
        urls_file: Path,
    ) -> tuple[list[str], bool]:
        """Return (http_methods, requires_auth) for a given view."""

        views_file = self._find_views_file(urls_file)
        if not views_file:
            return self._default_methods(view_name), False

        try:
            source = views_file.read_text(errors="ignore")
            tree   = ast.parse(source)
        except Exception:
            return self._default_methods(view_name), False

        for node in ast.walk(tree):

            # Class-based view
            if isinstance(node, ast.ClassDef) and node.name == view_name:
                methods      = self._extract_methods_from_class(node)
                requires_auth = self._check_auth_in_class(node)
                return methods, requires_auth

            # Function-based view
            if isinstance(node, ast.FunctionDef) and node.name == view_name:
                methods      = self._extract_methods_from_fbv(node)
                requires_auth = self._check_auth_in_fbv(node)
                return methods, requires_auth

        return self._default_methods(view_name), False

    def _extract_methods_from_class(self, node: ast.ClassDef) -> list[str]:
        """Extract HTTP methods from def get/post/put/delete in class."""
        http = {"get", "post", "put", "patch", "delete", "head", "options"}
        found = [
            item.name.upper()
            for item in node.body
            if isinstance(item, ast.FunctionDef)
            and item.name.lower() in http
        ]
        return found if found else ["GET"]

    def _extract_methods_from_fbv(self, node: ast.FunctionDef) -> list[str]:
        """Extract methods from @api_view(['GET', 'POST']) decorator."""
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if self._get_call_name(decorator) == "api_view":
                    if decorator.args:
                        arg = decorator.args[0]
                        if isinstance(arg, ast.List):
                            return [
                                elt.value
                                for elt in arg.elts
                                if isinstance(elt, ast.Constant)
                            ]
        return ["GET"]

    def _check_auth_in_class(self, node: ast.ClassDef) -> bool:
        """Check if permission_classes contains an auth class."""
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if self._get_name(target) == "permission_classes":
                        src = ast.unparse(item.value)
                        if any(cls in src for cls in self.AUTH_CLASSES):
                            return True
        return False

    def _check_auth_in_fbv(self, node: ast.FunctionDef) -> bool:
        """Check @permission_classes decorator on FBV."""
        for decorator in node.decorator_list:
            src = ast.unparse(decorator)
            if any(cls in src for cls in self.AUTH_CLASSES):
                return True
        return False

    def _default_methods(self, view_name: str) -> list[str]:
        """Guess HTTP method from view name as fallback."""
        name = view_name.lower()
        if "list" in name or "detail" in name: return ["GET"]
        if "create" in name: return ["POST"]
        if "update" in name: return ["PUT", "PATCH"]
        if "destroy" in name or "delete" in name: return ["DELETE"]
        return ["GET"]

    #  FILE RESOLUTION

    def _find_views_file(self, urls_file: Path) -> Path | None:
        """Find views.py for a given urls.py."""

        # Strategy 1 — same directory
        candidate = urls_file.parent / "views.py"
        if candidate.exists():
            return candidate

        # Strategy 2 — read imports in urls.py
        try:
            source = urls_file.read_text(errors="ignore")
            tree   = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if "views" in module:
                        resolved = self._resolve_module_to_file(module)
                        if resolved:
                            return resolved
                    # relative import: from .views import ...
                    if node.level > 0 and module == "views":
                        candidate = urls_file.parent / "views.py"
                        if candidate.exists():
                            return candidate
        except Exception:
            pass

        return None

    def _resolve_module_to_file(self, module_path: str) -> Path | None:
        """
        Convert module string to file path.
        "apps.user.urls" → repo/apps/user/urls.py
        """
        module_path = module_path.strip("'\"").strip()

        # Direct conversion
        direct = self.repo_path / Path(
            module_path.replace(".", "/") + ".py"
        )
        if direct.exists():
            return direct

        # Try progressively shorter paths
        parts = module_path.split(".")
        for i in range(len(parts)):
            partial   = Path(*parts[i:]).with_suffix(".py")
            candidate = self.repo_path / partial
            if candidate.exists():
                return candidate

        # Full recursive search as last resort
        file_name = parts[-1] + ".py"
        for candidate in sorted(self.repo_path.rglob(file_name)):
            if not self._should_skip(candidate):
                return candidate

        return None

    #  DUPLICATE CHECKER
    def _check_duplicates(self) -> None:
        """Warn about duplicate URL patterns."""
        seen: dict[str, str] = {}
        for ep in self.endpoints:
            key = ep.url_pattern
            if key in seen:
                console.print(
                    f"  [yellow]⚠ Duplicate pattern:[/yellow] "
                    f"{ep.url_pattern} "
                    f"({seen[key]} and {ep.view_name})"
                )
            else:
                seen[key] = ep.view_name

    #  AST UTILITIES
    def _should_skip(self, path: Path) -> bool:
        return any(p in path.parts for p in self.SKIP_DIRS)

    def _get_name(self, node) -> str | None:
        if isinstance(node, ast.Name):      return node.id
        if isinstance(node, ast.Attribute): return node.attr
        return None

    def _get_call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):      return node.func.id
        if isinstance(node.func, ast.Attribute): return node.func.attr
        return ""

    def _extract_first_arg(self, node: ast.Call) -> str | None:
        if node.args and isinstance(node.args[0], ast.Constant):
            return str(node.args[0].value)
        return None

    def _get_nth_arg(self, node: ast.Call, n: int):
        return node.args[n] if len(node.args) > n else None

    def _has_include(self, node: ast.Call) -> bool:
        second = self._get_nth_arg(node, 1)
        return (
            second is not None
            and isinstance(second, ast.Call)
            and self._get_call_name(second) == "include"
        )

    def _extract_include_path(self, node: ast.Call) -> str | None:
        """Extract module path string from include('app.urls')"""
        include_call = None

        if self._get_call_name(node) == "include":
            include_call = node
        else:
            second = self._get_nth_arg(node, 1)
            if (
                second
                and isinstance(second, ast.Call)
                and self._get_call_name(second) == "include"
            ):
                include_call = second

        if not include_call:
            return None

        if include_call.args and isinstance(include_call.args[0], ast.Constant):
            return str(include_call.args[0].value)

        return None

    def _extract_view_name(self, node: ast.Call) -> str | None:
        """Extract view name from path('url/', SomeView.as_view())"""
        second = self._get_nth_arg(node, 1)
        if second is None:
            return None

        # SomeView.as_view() → "SomeView"
        if isinstance(second, ast.Call):
            if (
                isinstance(second.func, ast.Attribute)
                and second.func.attr == "as_view"
            ):
                return self._get_name(second.func.value)
            return self._get_call_name(second)

        if isinstance(second, ast.Name):      return second.id
        if isinstance(second, ast.Attribute): return second.attr
        return None

    def _extract_list_items(self, node) -> list:
        """Handle list and list + list concatenation."""
        if isinstance(node, ast.List):
            return node.elts
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return (
                self._extract_list_items(node.left)
                + self._extract_list_items(node.right)
            )
        return []