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
            console.print(
                f"  [dim]Return code:[/dim] {result.returncode}"
            )

            results = self._parse_results(output)
            return results, output

        except subprocess.TimeoutExpired:
            console.print(f"  [red]✗ Timeout for {app_name}[/red]")
            return [], "ERROR: Timeout"
        except Exception as e:
            console.print(f"  [red]✗ Error:[/red] {e}")
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

    def _parse_results(self, output: str) -> list[TestResult]:
        """Parse Django test output."""
        results = []

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

            if raw_status.startswith("SKIPPED"):
                status = "SKIPPED"
            else:
                status = status_map.get(raw_status, "ERROR")

            app_name = ""
            for part in module.split("."):
                if part.startswith("test") or part == "tests":
                    continue
                app_name = part
                break

            results.append(TestResult(
                endpoint = EndpointInfo(
                    url_pattern   = test_name,
                    http_methods  = [],
                    view_name     = test_name,
                    requires_auth = False,
                    app_name      = app_name,
                ),
                status        = status,
                response_code = 0,
                expected_code = 0,
                error_message = (
                    self._extract_error(output, test_name)
                    if status in ("FAILED", "ERROR")
                    else None
                ),
            ))

        if not results:
            has_error = "ERROR" in output
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