import venv
import os
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime
from rich.console import Console
from ai_tester.models import TestResult, EndpointInfo

console = Console()

class AppTestRunner:
    """
    Runs tests for ONE app at a time.
    Uses the app's own tests.py file.
    """

    VENV_DIR = ".probe_venv"

    def __init__(self, repo_path: str):
        self.repo_path  = Path(repo_path)
        self.venv_path  = self.repo_path / self.VENV_DIR
        self.python     = self._get_python_path()
        self.errors_dir = Path.home() / ".djangoprobe" / "errors"
        self.errors_dir.mkdir(parents=True, exist_ok=True)

        self._setup_venv()
        self._install_dependencies()

    def _get_python_path(self) -> Path:
        import sys
        if sys.platform == "win32":
            return self.venv_path / "Scripts" / "python.exe"
        return self.venv_path / "bin" / "python"

    def run_single_app(self, app_name: str) -> tuple:
        """
        Run tests for a single app.
        Returns (list[TestResult], raw_output)
        """
        console.print(f"  [dim]Running tests for:[/dim] {app_name}")

        # Find the app module from installed apps
        # e.g. "user" → "apps.user"
        app_module = self._get_app_module(app_name)

        env = os.environ.copy()
        env_file = self.repo_path / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                if "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip().strip('"').strip("'")

        try:
            result = subprocess.run(
                [
                    str(self.python),
                    "manage.py",
                    "test",
                    app_module,
                    "--verbosity=2",
                    "--keepdb",
                ],
                cwd = str(self.repo_path),
                capture_output = True,
                text = True,
                timeout = 120,  # 2 min per app
                env = env,
            )

            output = result.stderr + "\n" + result.stdout

            for line in output.split("\n"):
                if line.startswith("Ran "):
                    console.print(f"  [dim]{line}[/dim]")
                if line.startswith("OK") or line.startswith("FAILED"):
                    color = "green" if line.startswith("OK") else "red"
                    console.print(f"  [{color}]{line}[/{color}]")

            results = self._parse_results(output, app_module)
            return results, output

        except subprocess.TimeoutExpired:
            return [], "ERROR: Timeout"
        except Exception as e:
            return [], f"ERROR: {e}"

    def save_app_errors(
        self,
        app_name: str,
        errors:   list,
        output:   str,
    ) -> None:
        """Save error details to JSON for this app."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path      = self.errors_dir / f"{app_name}_{timestamp}.json"

        data = {
            "app":          app_name,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_count":  len(errors),
            "errors": [
                {
                    "test":   r.endpoint.url_pattern,
                    "status": r.status,
                    "error":  r.error_message,
                }
                for r in errors
            ],
            "raw_output": output[-2000:],  # last 2000 chars
        }

        path.write_text(json.dumps(data, indent=2))
        console.print(
            f"  [dim]Errors saved:[/dim] {path}"
        )

    def _get_app_module(self, app_name: str) -> str:
        """
        Find full module path for app.
        "user" → "apps.user"
        """
        settings_file = self._find_settings()
        if not settings_file:
            return app_name

        content = settings_file.read_text(errors="ignore")
        match   = re.search(
            r"INSTALLED_APPS\s*=\s*\[([^\]]*)\]",
            content, re.DOTALL
        )
        if not match:
            return app_name

        apps = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
        for app in apps:
            if app.endswith(f".{app_name}") or app == app_name:
                return app

        return app_name

    def _find_settings(self) -> Path | None:
        skip = {"venv", "env", "site-packages", "__pycache__", ".git"}
        for candidate in self.repo_path.rglob("settings.py"):
            if not any(p in candidate.parts for p in skip):
                return candidate
        return None

    def _parse_results(self, output: str, app_module: str = "") -> list[TestResult]:
        results = []

        # Pattern: test_name (module.Class) ... ok/FAIL/ERROR
        pattern = re.compile(
            r"^(test\w+)\s+\(([^)]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR|skipped.*?)$",
            re.MULTILINE | re.IGNORECASE,
        )

        status_map = {
            "OK":    "PASSED",
            "FAIL":  "FAILED",
            "ERROR": "ERROR",
        }

        for match in pattern.finditer(output):
            test_name  = match.group(1)
            module     = match.group(2)
            raw_status = match.group(3).strip().upper()

            status = "SKIPPED" if raw_status.startswith("SKIPPED") \
                    else status_map.get(raw_status, "ERROR")

            # Extract app name from module
            app_name = ""
            for part in module.split("."):
                if part not in ("tests", "test") and not part.startswith("Test"):
                    app_name = part
                    break

            # Extract error details for failed tests
            error_msg = None
            if status in ("FAILED", "ERROR"):
                error_msg = self._extract_error(output, test_name)

            # Extract URL from test name
            # test_login_user → /api/user/login/
            url = self._url_from_test_name(test_name, app_name)

            results.append(TestResult(
                endpoint = EndpointInfo(
                    url_pattern   = url,
                    http_methods  = self._method_from_test_name(test_name),
                    view_name     = test_name,
                    requires_auth = False,
                    app_name      = app_name,
                ),
                status        = status,
                response_code = self._code_from_error(error_msg),
                expected_code = self._expected_code_from_test(test_name),
                error_message = error_msg,
            ))

        # Fallback
        if not results:
            has_error = "ERROR" in output or "error" in output.lower()
            results.append(TestResult(
                endpoint = EndpointInfo(
                    url_pattern   = "/",
                    http_methods  = [],
                    view_name     = "unknown",
                    requires_auth = False,
                    app_name      = "unknown",
                ),
                status        = "ERROR" if has_error else "PASSED",
                response_code = 0,
                expected_code = 0,
                error_message = output[-500:] if has_error else None,
            ))

        return results
    def _url_from_test_name(self, test_name: str, app_name: str) -> str:
        """Guess URL from test name."""
        name = test_name
        for prefix in ["test_"]:
            if name.startswith(prefix):
                name = name[len(prefix):]

        # Remove common suffixes
        for suffix in [
            "_success", "_failure", "_error",
            "_valid", "_invalid", "_empty",
            "_auth", "_no_auth", "_without_auth",
            "_create", "_list", "_detail",
            "_update", "_delete", "_bulk",
        ]:
            name = name.replace(suffix, "")

        return f"/api/{name.replace('_', '/')}/"
    def _method_from_test_name(self, test_name: str) -> list[str]:
        """Guess HTTP method from test name."""
        name = test_name.lower()
        if "create" in name or "post" in name:   return ["POST"]
        if "update" in name or "put" in name:    return ["PUT"]
        if "delete" in name:                      return ["DELETE"]
        if "patch" in name:                       return ["PATCH"]
        return ["GET"]

    def _code_from_error(self, error_msg: str | None) -> int:
        """Extract actual status code from error message."""
        if not error_msg:
            return 200
        match = re.search(r"(\d{3}) != \d{3}", error_msg)
        if match:
            return int(match.group(1))
        return 0

    def _expected_code_from_test(self, test_name: str) -> int:
        """Guess expected code from test name."""
        name = test_name.lower()
        if "create" in name:  return 201
        if "delete" in name:  return 200
        if "login" in name:   return 200
        if "invalid" in name: return 400
        if "no_auth" in name: return 401
        return 200

    def _extract_error(self, output: str, test_name: str) -> str | None:
        pattern = re.compile(
            rf"(?:FAIL|ERROR):\s+{re.escape(test_name)}.*?\n(.*?)"
            rf"(?=\n(?:FAIL|ERROR|OK|Ran|\-{{70}}))",
            re.DOTALL,
        )
        match = pattern.search(output)
        if match:
            return match.group(1).strip()[:500]
        return None
    def _setup_venv(self) -> None:
      if self.venv_path.exists():
          console.print(f"  [dim]Using existing venv:[/dim] {self.VENV_DIR}")
          return
      console.print(f"  [dim]Creating venv:[/dim] {self.VENV_DIR}")
      venv.create(str(self.venv_path), with_pip=True, clear=True)
      console.print("  [green]✓ Venv created[/green]")

    def _install_dependencies(self) -> None:
        req_file = self.repo_path / "requirements.txt"
        if not req_file.exists():
            return
        console.print("  [dim]Installing dependencies...[/dim]")
        subprocess.run(
            [str(self.python), "-m", "pip", "install",
            "-r", str(req_file), "--quiet",
            "--disable-pip-version-check"],
            cwd=str(self.repo_path),
            capture_output=True,
            timeout=300,
        )
        console.print("  [green]✓ Dependencies installed[/green]")