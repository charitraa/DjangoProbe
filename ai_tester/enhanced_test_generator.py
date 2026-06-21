import re
import time
from pathlib import Path
from rich.console import Console
from ai_tester.models import EndpointInfo
from ai_tester.ai_helper import AIHelper

console = Console()

# A password strong enough to pass Django's default AUTH_PASSWORD_VALIDATORS
# (min length, not all-numeric, not a common password, not similar to the
# username/email). Registration endpoints run these validators, so weak
# defaults like "password123" make create/register success tests return 400.
STRONG_TEST_PASSWORD = "Str0ng!Pass99"


class EnhancedTestGenerator:
    """
    Single-step, raw-code test generator.

    For each app it:
    1. Reads the app's RAW source (models/serializers/views/urls + any
       services/repositories/permissions/etc., file or package).
    2. Makes ONE LLM call with that source plus a short, accurate prompt
       (real login URL/credential field, pagination shape, DRF facts).
    3. Lightly cleans the output and validates it.
    4. Applies a small write-time safety net (_final_sanitize) and writes the file.

    Usage:
        generator = EnhancedTestGenerator(repo_path, endpoints, analysis)
        test_files = generator.generate()
    """

    MAX_TOKENS = 16000  # Max tokens for generation; high enough that a full test file is not truncated mid-code

    def __init__(
        self,
        repo_path: str,
        endpoints: list[EndpointInfo],
        analysis=None,  # ProjectAnalysis
    ):
        self.repo_path = Path(repo_path)
        self.endpoints = endpoints
        self.analysis = analysis
        self.output_dir = self.repo_path / "tests" / "generated"
        self.ai_helper = AIHelper(str(self.repo_path), analysis=analysis)
        # Build app module map for correct imports
        self.app_module_map = self._build_app_module_map()

    def _build_app_module_map(self) -> dict[str, str]:
        """Build mapping of app last-segment names to their full module paths.

        `ai_helper.installed_apps` is a list of dicts: {module, app_name, app_dir}.
        The previous implementation treated each entry as a string and silently
        produced an empty map — which broke both the prompt's import guidance and
        the hallucinated-import validator.
        """
        return {
            app["app_name"]: app["module"]
            for app in self.ai_helper.installed_apps
            if app.get("app_name") and app.get("module")
        }

    # PUBLIC
    def generate(self) -> list[str]:
        """
        Generate test files for all endpoints, one app at a time.

        Each app: read its raw source → one LLM call → clean/validate → write.
        """
        if not self.endpoints:
            console.print(
                "[yellow]⚠ No endpoints — nothing to generate[/yellow]"
            )
            return []

        self._setup_output_dir()
        app_groups = self._group_by_app()

        console.print(
            f"\n  [dim]Analyzing and generating tests for "
            f"{len(app_groups)} app(s)...[/dim]"
        )

        generated_files: list[str] = []

        for app_name, app_endpoints in app_groups.items():
            file_path = self._generate_for_app(app_name, app_endpoints)
            if file_path:
                generated_files.append(file_path)
            time.sleep(2)  # Brief _setup_output_dirpause between apps to avoid rate limits

        return generated_files

    # PER-APP GENERATION
    def generate_for_app(
        self,
        app_name: str,
        app_endpoints: list[EndpointInfo],
    ) -> str | None:
        """Public entry point: generate the test file for one app."""

        return self._generate_for_app(app_name, app_endpoints)

    def _generate_for_app(
        self,
        app_name: str,
        app_endpoints: list[EndpointInfo],
    ) -> str | None:
        """Read raw source → one LLM call → clean/validate → write, for one app."""
        console.print(
            f"\n  [bold cyan]{'='*60}[/bold cyan]"
        )
        console.print(
            f"  [bold cyan]Processing App:[/bold cyan] [green]{app_name}[/green] "
            f"[dim]({len(app_endpoints)} endpoints)[/dim]"
        )
        console.print(
            f"  [bold cyan]{'='*60}[/bold cyan]"
        )

        file_path = self.output_dir / f"test_{app_name}.py"

        # Step 1: Read the app's RAW source (no lossy LLM summary step).
        sources = self._read_app_sources(app_name)
        if not any(sources.values()):
            console.print(
                f"  [red]✗ Could not read source files for {app_name}[/red]"
            )
            return None
        console.print(
            f"  [dim]→ Read {sum(1 for v in sources.values() if v)} source file(s) for {app_name}[/dim]"
        )

        # Step 2: One LLM call — raw code + a short, accurate prompt.
        console.print(f"\n  [dim]→ Generating tests from raw source...[/dim]")
        content = self._generate_tests_from_raw(app_name, app_endpoints, sources)
        if not content:
            console.print(
                f"  [red]✗ Failed to generate tests for {app_name}[/red]"
            )
            return None

        content = self._clean_code_light(content)

        # Step 2.5: Validate; on syntax failure, one retry.
        validated, content = self._validate_generated_code(content, app_name)
        if not validated:
            console.print(f"  [yellow]→ Validation failed, retrying once...[/yellow]")
            content = self._generate_tests_from_raw(app_name, app_endpoints, sources)
            if not content:
                console.print(f"  [red]✗ Retry generation failed for {app_name}[/red]")
                return None
            content = self._clean_code_light(content)
            validated, content = self._validate_generated_code(content, app_name)
            if not validated:
                console.print(f"  [red]✗ Retry also failed for {app_name}[/red]")
                return None

        # Step 3: Write to file (the write choke point applies _final_sanitize).
        written = self._write_test_file(app_name, content, file_path)
        return written

    # RAW SINGLE-STEP GENERATION
    # Modules that describe an app's API surface + business logic, in the order
    # we want the model to read them. Each may be a single .py file OR a package
    # (a folder of the same name, e.g. models/ or services/).
    _SOURCE_MODULES = (
        "models", "serializers", "views", "viewsets", "urls", "api",
        "services", "service", "repositories", "repository", "selectors",
        "permissions", "filters", "managers", "querysets", "validators",
        "choices", "enums", "constants", "schemas", "forms", "tasks", "utils",
    )
    # Skip noise and anything huge/irrelevant.
    _SOURCE_SKIP = {"__pycache__", "migrations", "tests", "test", "__init__.py"}
    _SOURCE_TOTAL_CAP = 28000   # chars; keeps the prompt within context for medium apps
    _SOURCE_FILE_CAP = 8000     # chars per file; truncate pathological files

    def _resolve_app_dir(self, app_name: str) -> Path | None:
        app = next((a for a in self.ai_helper.installed_apps
                    if a.get("app_name") == app_name), None)
        if app and app.get("app_dir") and Path(app["app_dir"]).exists():
            return Path(app["app_dir"])
        if (self.repo_path / app_name).exists():
            return self.repo_path / app_name
        return None

    def _read_app_sources(self, app_name: str) -> dict[str, str]:
        """Read the app's raw source — the ground truth for test generation.

        Grabs models/serializers/views/urls plus any service, repository,
        permission, selector, filter (etc.) modules, whether each is a single
        ``.py`` file or a package directory. This is what lets the model write
        correct tests for medium DRF projects that have a service/repo layer.
        """
        app_dir = self._resolve_app_dir(app_name)
        sources: dict[str, str] = {}
        if app_dir is None:
            return sources

        total = 0

        def add(label: str, path: Path) -> None:
            nonlocal total
            if total >= self._SOURCE_TOTAL_CAP:
                return
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                return
            if not text.strip():
                return
            if len(text) > self._SOURCE_FILE_CAP:
                text = text[:self._SOURCE_FILE_CAP] + "\n# ...(truncated)...\n"
            sources[label] = text
            total += len(text)

        for name in self._SOURCE_MODULES:
            pyfile = app_dir / f"{name}.py"
            if pyfile.exists():
                add(f"{name}.py", pyfile)
            pkg = app_dir / name
            if pkg.is_dir():
                for f in sorted(pkg.glob("*.py")):
                    if f.name in self._SOURCE_SKIP:
                        continue
                    add(f"{name}/{f.name}", f)
        return sources

    def _clean_code_light(self, content: str) -> str:
        """Minimal cleanup: strip markdown fences and any leading prose.

        The heavy regex layer is intentionally skipped — the raw-code prompt
        produces correct code, and the write-time ``_final_sanitize`` still
        guards the few fatal patterns (self.str, undefined User, bare setUp
        refs, login URL).
        """
        content = content.strip()
        if content.startswith("```python"):
            content = content[len("```python"):].strip()
        elif content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        # Drop any preamble before the first import/from.
        m = re.search(r'^(from |import )', content, re.MULTILINE)
        if m and m.start() > 0:
            content = content[m.start():]
        return content

    def _generate_tests_from_raw(
        self,
        app_name: str,
        app_endpoints: list[EndpointInfo],
        sources: dict[str, str],
    ) -> str | None:
        """Single LLM call: raw app source + a short, accurate prompt."""
        a = self.analysis
        module = self.app_module_map.get(app_name, app_name)
        login_url = (a.login_url if a and a.login_url else "/api/auth/login/")
        cred = (a.username_field if a and a.username_field else "username")
        auth_type = (a.auth_type if a else "JWT")
        paginated = self._is_pagination_enabled()
        list_shape = (
            "a paginated dict: {'count', 'next', 'previous', 'results': [...]} — read items from response.json()['results']"
            if paginated else
            "a plain JSON array: [ {...}, ... ] — response.json() is a list, NOT a dict (do not use ['results'])"
        )

        if auth_type and auth_type.upper() == "JWT":
            auth_rules = (
                f"- Auth: JWT (Bearer). In setUp, create a user with get_user_model().objects.create_user(...),\n"
                f"  then POST to '{login_url}' with {{'{cred}': <{cred}>, 'password': <password>}}, read the\n"
                f"  'access' token from the JSON, and set self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'.\n"
                f"- The login credential field is '{cred}'. Use that user's '{cred}' value (not their email unless '{cred}' is email).\n"
                f"- Invalid/non-existent login returns 401 (SimpleJWT), NOT 400. No token / bad token on a protected endpoint = 401.\n"
                f"- Do NOT use APIClient, force_authenticate(), or client.login()."
            )
        else:
            auth_rules = (
                f"- Auth: session. Create the user, then self.client.login({cred}=<value>, password=<password>)."
            )

        src_blocks = "\n".join(
            f"### {fname}\n```python\n{code.strip()}\n```"
            for fname, code in sources.items() if code.strip()
        )
        endpoint_lines = "\n".join(
            f"- {', '.join(ep.http_methods)} {ep.url_pattern}"
            f"{' [auth required]' if ep.requires_auth else ' [public]'}"
            for ep in app_endpoints
        )

        system_prompt = (
            "You are an expert Django REST Framework test engineer. You are given the "
            "REAL source code of one app. Write a complete, correct Django TestCase file "
            "that exercises its API endpoints over HTTP. Return ONLY Python code — no "
            "markdown fences, no prose."
        )

        user_prompt = f"""Write a Django test file for the "{app_name}" app, based on its real source code below.

## Source code
{src_blocks}

## Endpoints to test
{endpoint_lines}

## Rules (follow exactly)
- Imports: `from django.test import TestCase, Client` and `import json`. Get the user model with
  `from django.contrib.auth import get_user_model` then `User = get_user_model()`.
- Use ABSOLUTE imports for this app's models: `from {module}.models import <Model>`. Never relative imports.
- Use the test Client with JSON: self.client.post(url, data=json.dumps(payload), content_type='application/json').
- Use the EXACT URL paths from urls.py above (login URL is '{login_url}'). End every URL with a trailing slash.
- Convert object ids/pks to str() inside URL f-strings: f'/api/.../{{str(obj.id)}}/'.
{auth_rules}
- List (GET collection) responses are {list_shape}.
- Read the serializer to know which fields are REQUIRED vs optional. Only a missing/empty REQUIRED field returns 400.
  Optional blank text fields come back as '' (empty string), not None.
- Read-only/server-set fields (id, owner, created_at, updated_at) are IGNORED in payloads (no 400). Don't assert their exact value — only assertIn('<field>', response.json()).
- write_only fields (e.g. 'password') are NEVER returned in the response body — use assertNotIn('password', response.json()), never assertIn. Never write contradictory assertions.
- Test ONLY the HTTP endpoints listed above. Do NOT test ORM internals (cascade deletes, signals, manager methods).
- Write a FOCUSED suite: for each endpoint cover the main success case plus the key
  failure cases (auth → 401 without token; validation → 400; not found → 404;
  ownership-scoped detail of another user's object → 404). Do NOT generate dozens of
  redundant edge-case permutations — prefer a clear, reliable suite of ~2-4 tests per endpoint.
- Every test method must be self-consistent: never put two contradictory assertions
  (e.g. assertIn and assertNotIn for the same key) in one test.

Return ONLY the complete Python test file."""

        response = self.ai_helper.call_with_retry(
            model=self.ai_helper.MODEL,
            max_tokens=self.MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content if response else None
        if not content or not content.strip():
            console.print(f"    [yellow]⚠ Empty response from model[/yellow]")
            return None
        console.print(f"    [green]✓ Generated {len(content)} chars of test code[/green]")
        return content



    def _is_pagination_enabled(self) -> bool:
        """Detect whether DRF list endpoints are paginated for this project.

        A list endpoint only returns a {'count', 'results': [...]} envelope when
        a default pagination class (or global PAGE_SIZE) is configured. Without
        it, DRF returns a plain JSON array — assuming 'results' then raises
        TypeError/KeyError in generated tests.
        """
        for settings_file in self.repo_path.rglob("settings.py"):
            if any(part in {"site-packages", ".venv", "env", ".probe_venv"}
                   for part in settings_file.parts):
                continue
            try:
                content = settings_file.read_text(errors="ignore")
            except OSError:
                continue
            if "DEFAULT_PAGINATION_CLASS" in content or "PAGE_SIZE" in content:
                return True
        return False





    # FILE WRITING
    def _final_sanitize(self, content: str) -> str:
        """Last-line-of-defense fixes applied at the single write choke point.

        ``_clean_code`` already handles these, but this guards against any code
        path (retries, syntax-fix salvage, partial regenerations) that could let
        a known-fatal pattern slip through to disk. These substitutions are all
        idempotent and safe to re-apply, so we run the must-be-correct passes
        here too — they are what actually prevents NameError/AttributeError at
        runtime regardless of how the content was produced.
        """
        # self.str(x) is not a method — collapse to the builtin str(x).
        content = re.sub(r'self\s*\.\s*str\s*\(', 'str(', content)
        # A reverse() to an unregistered namespace (e.g. "api:auth:login") raises
        # NoReverseMatch and errors the whole module — map login reverses to the
        # detected login URL.
        if self.analysis and self.analysis.login_url:
            login_url = self.analysis.login_url
            content = re.sub(
                r"reverse\(\s*['\"][^'\"]*login[^'\"]*['\"]\s*\)",
                f"'{login_url}'",
                content,
            )
            # Normalise any login-path string literal (e.g. a variable like
            # self.login_url = '/auth/login/' that dropped the '/api' include
            # prefix) to the detected login URL. Matches URL-path literals
            # containing 'login'; the register/other URLs don't contain it.
            content = re.sub(
                r"(['\"])/[A-Za-z0-9_/-]*login[A-Za-z0-9_/-]*/?\1",
                f"'{login_url}'",
                content,
            )
        # Guarantee User is defined when referenced.
        content = self._ensure_user_defined(content)
        # Prefix bare references to setUp instance attributes with self.
        content = self._fix_missing_self_references(content)
        return content

    def _write_test_file(
        self,
        app_name: str,
        content: str,
        file_path: Path,
    ) -> str:
        """Write test file to disk with backup support."""

        content = self._final_sanitize(content)

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")

            # Same content — skip silently
            if existing.strip() == content.strip():
                console.print(
                    f"  [dim]↔ No changes:[/dim] test_{app_name}.py"
                )
                return str(file_path)

            # Different — tell user + backup
            console.print(
                f"  [yellow]⚠ Existing test found for:[/yellow] {app_name}"
            )

            backup_path = self._backup_file(app_name, existing)

            console.print(
                f"  [yellow]↺ Old version backed up →[/yellow] "
                f"tests/generated/backup/{backup_path.name}"
            )
            console.print(
                f"  [dim]Writing new version...[/dim]"
            )

        # Write new content
        file_path.write_text(content, encoding="utf-8")
        console.print(
            f"  [green]✓ Written:[/green] tests/generated/test_{app_name}.py"
        )

        return str(file_path)

    def _backup_file(self, app_name: str, content: str) -> Path:
        """Backup existing file with timestamp."""
        from datetime import datetime

        backup_dir = self.output_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"test_{app_name}_{timestamp}.py"
        backup_path.write_text(content, encoding="utf-8")

        return backup_path

    # SETUP
    def _setup_output_dir(self) -> None:
        """Create output directory and __init__.py files."""

        self.output_dir.mkdir(parents=True, exist_ok=True)

        tests_init = self.repo_path / "tests" / "__init__.py"
        if not tests_init.exists():
            tests_init.write_text("# Auto-generated by DjangoProbe\n")

        gen_init = self.output_dir / "__init__.py"
        if not gen_init.exists():
            gen_init.write_text("# Auto-generated by DjangoProbe\n")

    def _clear_existing_tests(self) -> None:
        """Clear all existing generated test files to force regeneration."""
        if self.output_dir.exists():
            for test_file in self.output_dir.glob("test_*.py"):
                try:
                    test_file.unlink()
                    console.print(f"  [yellow]🗑️ Deleted:[/yellow] {test_file.name}")
                except Exception as e:
                    console.print(f"  [yellow]⚠ Could not delete {test_file.name}: {e}[/yellow]")

    # HELPERS
    def _group_by_app(self) -> dict[str, list[EndpointInfo]]:
        """Group endpoints by app name."""
        groups: dict[str, list[EndpointInfo]] = {}
        for ep in self.endpoints:
            groups.setdefault(ep.app_name, []).append(ep)
        return groups

    def _validate_generated_code(self, content: str, app_name: str) -> tuple[bool, str]:
        """
        Validate that the generated code is complete and syntactically correct.

        Returns:
            Tuple of (is_valid, cleaned_content)
        """
        console.print(f"    [dim]→ Validating generated code...[/dim]")

        # Check for basic Python syntax
        try:
            compile(content, f'<test_{app_name}>', 'exec')
        except SyntaxError as e:
            console.print(f"    [red]✗ Syntax error in generated code: {e}[/red]")
            # Try to provide more specific error location
            if hasattr(e, 'lineno'):
                console.print(f"    [red]  Error at line {e.lineno}: {e.msg}[/red]")

            # Attempt to fix the syntax error automatically
            console.print(f"    [yellow]→ Attempting to fix syntax error...[/yellow]")
            fixed_content = self._fix_syntax_error(content, e)

            # Try compiling the fixed code
            try:
                compile(fixed_content, f'<test_{app_name}>', 'exec')
                console.print(f"    [green]✓ Syntax error fixed successfully[/green]")
                return True, fixed_content
            except SyntaxError:
                # Last-ditch: drop trailing junk and keep the longest valid prefix.
                # Only accept it if the salvaged code still has a TestCase + test_ method,
                # otherwise we'd hand back a no-op file that runs zero tests.
                salvaged = self._truncate_to_valid_prefix(content)
                if salvaged and 'TestCase' in salvaged and 'def test_' in salvaged:
                    dropped = content.count('\n') - salvaged.count('\n')
                    console.print(
                        f"    [green]✓ Salvaged by dropping {dropped} trailing line(s)[/green]"
                    )
                    return True, salvaged
                console.print(f"    [red]✗ Could not fix syntax error[/red]")
                return False, content

        # Pattern 2: Unmatched brackets/parentheses
        # (the compile() check above already catches real "missing colon" syntax errors;
        # the previous heuristic regex matched normal dict literals and produced a
        # false-positive warning on every successful app.)
        if content.count('{') != content.count('}'):
            console.print(f"    [yellow]⚠ Unmatched curly braces in code[/yellow]")
        if content.count('[') != content.count(']'):
            console.print(f"    [yellow]⚠ Unmatched square brackets in code[/yellow]")
        if content.count('(') != content.count(')'):
            console.print(f"    [yellow]⚠ Unmatched parentheses in code[/yellow]")

        # Pattern 3: Malformed function definitions
        malformed_def = re.findall(r'def\s+\w+\([^)]*\s*\n\s*[^\s:]', content)
        if malformed_def:
            console.print(f"    [yellow]⚠ Malformed function definitions found - missing colons[/yellow]")

        # Check for required imports
        required_imports = ['from django.test import', 'import json']
        for required in required_imports:
            if required not in content:
                console.print(f"    [yellow]⚠ Missing required import: {required}[/yellow]")

        # Check for TestCase class
        if 'class' not in content or 'TestCase' not in content:
            console.print(f"    [yellow]⚠ No TestCase class found[/yellow]")
            return False, content

        # Check for test methods
        if 'def test_' not in content:
            console.print(f"    [yellow]⚠ No test methods found[/yellow]")
            return False, content

        # Check for strict assertions that might fail due to User model behavior differences
        # Some User models set is_staff/is_superuser automatically based on role
        if 'self.assertFalse(user.is_staff)' in content:
            console.print(f"    [yellow]⚠ Test assumes user.is_staff=False - User model may set this automatically[/yellow]")
        if 'self.assertFalse(user.is_superuser)' in content:
            console.print(f"    [yellow]⚠ Test assumes user.is_superuser=False - User model may set this automatically[/yellow]")

        # Check for relative imports (bad)
        if 'from .models import' in content or 'from .serializers import' in content:
            console.print(f"    [red]✗ Found relative imports - use absolute imports instead[/red]")
            return False, content

        # Check for wrong User import
        if 'from django.contrib.auth.models import User' in content:
            console.print(f"    [red]✗ Found django.contrib.auth.models.User - use custom User model[/red]")
            return False, content

        # REMOVED: Check for incorrect self.str() calls
        # The cleaning function handles this automatically with regex substitutions
        # This validation was causing false positives and skipping valid code
        # The cleaning regex patterns already handle: self.str(, self.str (, self.  str(
        # No need to validate here since it's handled during cleaning

        # Check for force_authenticate (bad)
        if 'force_authenticate' in content:
            console.print(f"    [red]✗ Found force_authenticate - use proper authentication method[/red]")
            return False, content

        # Check for JWT authentication if the project uses JWT
        if self.analysis and self.analysis.auth_type == "JWT":
            if 'client.login(' in content:
                console.print(f"    [yellow]⚠ Found client.login() in JWT project - should use JWT authentication[/yellow]")
            # Check for JWT token handling
            if 'HTTP_AUTHORIZATION' not in content and 'Bearer' not in content:
                console.print(f"    [yellow]⚠ JWT project missing Authorization header handling[/yellow]")
            # Bearer-token (header) auth is the default; cookie support is optional.
        else:
            # Check for session authentication if not JWT
            if 'HTTP_AUTHORIZATION' not in content and 'Bearer' not in content:
                if 'authenticate' not in content and 'client.login' not in content:
                    console.print(f"    [yellow]⚠ No authentication method found in tests[/yellow]")

        # Check for UUID string conversion
        if 'UUID' in content or 'uuid' in content:
            # Check if there's any str() conversion for UUID-like operations
            has_str_conversion = 'str(' in content and ('id' in content or '.id' in content)
            if has_str_conversion:
                console.print(f"    [green]✓ Found str() conversion - good for UUID handling[/green]")

        # Check for proper structure
        if not all([
            'setUp' in content,
            'def test_' in content,
            'self.client' in content,
        ]):
            console.print(f"    [yellow]⚠ Code may be missing essential test structure[/yellow]")

        console.print(f"    [green]✓ Code validation passed[/green]")
        return True, content



    def _fix_syntax_error(self, content: str, error: SyntaxError) -> str:
        """
        Attempt to fix syntax errors in generated code.

        Args:
            content: The generated code with syntax errors
            error: The SyntaxError object

        Returns:
            Fixed code (may still have errors)
        """
        lines = content.split('\n')
        line_num = error.lineno if hasattr(error, 'lineno') else 0

        # Fix specific patterns based on error message
        if "unmatched ')'" in str(error).lower() or "unmatched '('" in str(error).lower():
            # Find and fix unmatched parentheses
            lines[line_num - 1] = self._fix_line_parens(lines[line_num - 1])
        elif "unexpected indent" in str(error).lower():
            # Fix indentation issues
            lines = self._fix_indentation(lines, line_num)
        elif "invalid syntax" in str(error).lower():
            # Try to fix various syntax issues
            lines[line_num - 1] = self._fix_invalid_syntax(lines[line_num - 1])

        return '\n'.join(lines)

    def _fix_line_parens(self, line: str) -> str:
        """Fix unmatched parentheses in a line."""
        # Fix 1: Missing closing parenthesis before quote in f-string
        if 'f\'' in line or 'f"' in line:
            # Pattern: f'/path/{str(id)}' -> f'/path/{str(id)})'
            # Check for unclosed str() calls in f-strings
            line = re.sub(r"f['\"]([^{\'\"]]*{str\([^)]+\)(?!\))", lambda m: m.group(0) + ")" if m.group(0).count('(') > m.group(0).count(')') else m.group(0), line)

        # Fix 2: Missing closing parenthesis before quote
        # Pattern: method('arg' -> method('arg')
        line = re.sub(r"(\w+)\('([^']*)'(?!\))", r"\1('\2')", line)
        line = re.sub(r'(\w+)\("([^"]*)"(?!\))', r'\1("\2")', line)

        # Fix 3: Add missing closing parentheses at end of line
        open_count = line.count('(')
        close_count = line.count(')')
        if open_count > close_count:
            # Add missing closing parentheses
            line += ')' * (open_count - close_count)

        # Fix 4: Fix str() calls that are missing closing parenthesis
        # Pattern: str(something' -> str(something)'
        line = re.sub(r'str\(([^)]*)\'$', r'str(\1)\'', line)
        line = re.sub(r'str\(([^)]*)"$', r'str(\1)"', line)

        return line

    def _fix_invalid_syntax(self, line: str) -> str:
        """Fix invalid syntax in a line."""
        # Fix 1: Missing colon after function definition
        if re.search(r'def\s+\w+\([^)]*\)\s*$', line):
            return line + ':'

        # Fix 2: Missing colon in dictionary
        if re.search(r'\{\s*\w+\s*[^:,\s\}]', line):
            # Find where colon should be added
            line = re.sub(r'(\{\s*\w+\s*)([^:,\s\}])', r'\1: \2', line)

        return line

    def _fix_indentation(self, lines: list[str], error_line: int) -> list[str]:
        """
        Fix indentation issues in generated code.

        Args:
            lines: List of code lines
            error_line: Line number where error occurred (1-indexed)

        Returns:
            Fixed list of lines
        """
        if error_line < 1 or error_line > len(lines):
            return lines

        # Determine expected indentation level
        # Look at the previous line to understand the context
        prev_line = lines[error_line - 2] if error_line > 1 else ""
        current_line = lines[error_line - 1]

        # Case 1: Previous line ends with colon, so we expect increased indentation
        if prev_line.rstrip().endswith(':'):
            # Calculate the expected indent (4 spaces or 1 tab per level)
            prev_indent = len(prev_line) - len(prev_line.lstrip())
            expected_indent = prev_indent + 4  # Add 4 spaces for next level
            current_indent = len(current_line) - len(current_line.lstrip())

            # If current line has less indentation than expected, fix it
            if current_indent < expected_indent:
                # Add the missing indentation
                lines[error_line - 1] = ' ' * (expected_indent - current_indent) + current_line

        # Case 2: Line is at same level as class/method definition but shouldn't be
        elif re.match(r'^\s*(class|def)\s+', prev_line):
            # This line should be indented (it's inside the class/method)
            prev_indent = len(prev_line) - len(prev_line.lstrip())
            current_indent = len(current_line) - len(current_line.lstrip())

            if current_indent <= prev_indent:
                # This line should be indented more
                lines[error_line - 1] = '    ' + current_line  # Add 4 spaces

        # Case 3: Fix mixed tabs and spaces
        if '\t' in current_line:
            # Convert tabs to spaces (4 spaces per tab)
            lines[error_line - 1] = current_line.replace('\t', '    ')

        return lines


    def _fix_missing_self_references(self, content: str) -> str:
        """Prefix bare references to setUp instance attributes with ``self.``.

        Models sometimes assign ``self.todo_a = ...`` in setUp() but then write
        ``todo_a`` (without ``self.``) inside a test method, raising NameError.
        We only rewrite names that are assigned exclusively as ``self.<name>``
        and never as a bare local ``<name> = ...`` — so genuine locals are left
        untouched.
        """
        instance_attrs = set(re.findall(r'\bself\.(\w+)\s*=', content))
        if not instance_attrs:
            return content

        local_assigns = set(re.findall(r'^[ \t]*(\w+)\s*=(?!=)', content, re.MULTILINE))

        # Candidates: assigned via self. only, never as a plain local, and not
        # dunder/short noise.
        candidates = {
            name for name in instance_attrs
            if name not in local_assigns and len(name) > 1 and not name.startswith('__')
        }
        if not candidates:
            return content

        for name in candidates:
            # Replace bare `name` only when it is used as an object — immediately
            # followed by an attribute access / call / subscript / separator
            # (`.`, `(`, `[`, `,`, `)`). This catches `todo_a.id`, `owner=todo_a)`
            # while leaving prose in docstrings/comments (e.g. "existing user")
            # untouched. Skips `self.name`, `x.name`, and longer names.
            content = re.sub(
                rf'(?<![\w.])(?<!self\.){name}(?=\s*[.\[(),])',
                f'self.{name}',
                content,
            )
        return content

    def _ensure_user_defined(self, content: str) -> str:
        """Guarantee the ``User`` symbol exists when the test references it.

        If the generated code uses ``User`` (e.g. ``User.objects.create_user``)
        but never imports or assigns it, inject the standard
        ``User = get_user_model()`` definition just after the import block so the
        module doesn't blow up with NameError at runtime.
        """
        uses_user = re.search(r'\bUser\b\s*[.(]', content)
        if not uses_user:
            return content

        # Already defined? (assignment, or imported as a name)
        if re.search(r'^\s*User\s*=', content, re.MULTILINE):
            return content
        if re.search(r'^\s*from\s+\S+\s+import\s+.*\bUser\b', content, re.MULTILINE):
            return content

        lines = content.split('\n')
        # Find the last top-level import line to insert after.
        insert_at = 0
        for i, line in enumerate(lines):
            if re.match(r'^\s*(import\s+\S+|from\s+\S+\s+import\s+)', line):
                insert_at = i + 1

        injection = [
            'from django.contrib.auth import get_user_model',
            'User = get_user_model()',
        ]
        lines[insert_at:insert_at] = injection
        return '\n'.join(lines)


    def _truncate_to_valid_prefix(self, content: str) -> str | None:
        """
        Find the longest leading prefix of `content` that parses as Python.

        Walks backwards from the end of the file, dropping one line at a time, until
        compile() succeeds. Returns the salvaged prefix, or None if no prefix parses
        (in which case the caller keeps the original).
        """
        lines = content.split('\n')
        for end in range(len(lines), 0, -1):
            candidate = '\n'.join(lines[:end])
            try:
                compile(candidate, '<truncate>', 'exec')
                return candidate
            except SyntaxError:
                continue
        return None



def generate_with_enhanced_analyzer(
    repo_path: str,
    endpoints: list[EndpointInfo],
    analysis=None,
    force_regenerate: bool = False,
) -> list[str]:
    """
    Convenience function to generate tests with enhanced AI-powered analysis.

    Args:
        repo_path: Path to the Django project
        endpoints: List of discovered endpoints
        analysis: ProjectAnalysis object (optional)
        force_regenerate: If True, delete existing test files before regenerating

    Returns:
        List of generated test file paths
    """
    generator = EnhancedTestGenerator(
        repo_path=repo_path,
        endpoints=endpoints,
        analysis=analysis,
    )

    if force_regenerate:
        generator._clear_existing_tests()

    return generator.generate()
