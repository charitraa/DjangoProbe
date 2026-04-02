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
    APP_TIMEOUT = 120  # 2 minutes per app for test execution
    ERROR_TIMEOUT = 300  # 5 minutes for error processing

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
        test_label = f"{app_module}.tests"
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
                    test_label,
                    "--verbosity=2",
                    "--keepdb",
                ],
                cwd = str(self.repo_path),
                capture_output = True,
                text = True,
                timeout=self.APP_TIMEOUT,  # 2 min per app
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

    def run_custom_test_label(self, test_label: str, app_name: str) -> tuple:
        """
        Run tests using a custom test label (for enhanced mode).
        Returns (list[TestResult], raw_output)
        """
        console.print(f"  [dim]Running tests for:[/dim] {test_label}")

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
                    test_label,
                    "--verbosity=2",
                    "--keepdb",
                ],
                cwd = str(self.repo_path),
                capture_output = True,
                text = True,
                timeout=self.APP_TIMEOUT,  # 2 min per app
                env = env,
            )

            output = result.stderr + "\n" + result.stdout

            for line in output.split("\n"):
                if line.startswith("Ran "):
                    console.print(f"  [dim]{line}[/dim]")
                if line.startswith("OK") or line.startswith("FAILED"):
                    color = "green" if line.startswith("OK") else "red"
                    console.print(f"  [{color}]{line}[/{color}]")

            # Parse results with the custom test label
            results = self._parse_results(output, test_label)
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
        """Save detailed error information to JSON for this app."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path      = self.errors_dir / f"{app_name}_{timestamp}.json"

        data = {
            "app":          app_name,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_count":  len(errors),
            "errors": [
                {
                    "test_name":     r.endpoint.view_name,
                    "app_name":      r.endpoint.app_name,
                    "url":           r.endpoint.url_pattern,
                    "http_methods":  r.endpoint.http_methods,
                    "status":        r.status,
                    "response_code": r.response_code,
                    "expected_code": r.expected_code,
                    "error_message": r.error_message,
                }
                for r in errors
            ],
            "raw_output": output[-5000:],  # last 5000 chars for context
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

        # Pattern for Django test output: ERROR/FAIL: test_name (module.Class.test_name)
        test_pattern = re.compile(
            r"^(ERROR|FAIL):\s+(test\w+)\s+\(([^)]+)\)\s*$",
            re.MULTILINE | re.IGNORECASE,
        )

        # Pattern for passed tests from "Ran X tests" and "OK" or "FAILED" summary
        summary_pattern = re.compile(
            r"^Ran\s+(\d+)\s+test.*?\n\s*(OK|FAILED|ERROR)",
            re.MULTILINE | re.IGNORECASE,
        )

        # Find all ERROR and FAIL test entries
        for match in test_pattern.finditer(output):
            status_type = match.group(1).upper()  # ERROR or FAIL
            test_name   = match.group(2)
            module_info = match.group(3)

            # Parse module info: apps.user.tests.AppTests.test_get_user_details
            parts = module_info.split(".")
            app_name = ""
            # Find the first app name part (not 'tests', not 'AppTests')
            for part in parts:
                if part not in ("tests", "test") and not part.startswith("AppTests") and not part.startswith("Test") and not part.endswith("tests"):
                    # Skip common framework modules like "apps" if there's a real app name after it
                    if part == "apps" and len(parts) > 3:
                        continue
                    app_name = part
                    break

            # Extract error details
            error_msg = self._extract_error(output, test_name)
            actual_code = self._extract_actual_code(error_msg)
            expected_code = self._extract_expected_code(error_msg)

            # Extract URL and HTTP method from test output (INFO lines)
            url, methods = self._extract_url_and_methods(output, test_name)

            # Fallback: extract URL/methods from test name if INFO lines not found
            if not url or not methods:
                fallback_url = self._url_from_test_name(test_name, app_name)
                fallback_methods = self._method_from_test_name(test_name)
                if not url:
                    url = fallback_url
                if not methods:
                    methods = fallback_methods

            results.append(TestResult(
                endpoint = EndpointInfo(
                    url_pattern   = url,
                    http_methods  = methods,
                    view_name     = test_name,
                    requires_auth = False,
                    app_name      = app_name,
                ),
                status        = status_type,
                response_code = actual_code,
                expected_code = expected_code,
                error_message = error_msg,
            ))

        # Count passed tests from summary
        if summary_pattern.search(output):
            summary_match = summary_pattern.search(output)
            total_tests = int(summary_match.group(1))
            failed_count = len(results)
            passed_count = total_tests - failed_count

            # Add placeholder results for passed tests
            for i in range(passed_count):
                results.append(TestResult(
                    endpoint = EndpointInfo(
                        url_pattern   = "passed_test",
                        http_methods  = [],
                        view_name     = f"passed_test_{i+1}",
                        requires_auth = False,
                        app_name      = app_module.split(".")[-1] if app_module else "unknown",
                    ),
                    status        = "PASSED",
                    response_code = 200,
                    expected_code = 200,
                    error_message = None,
                ))

        # Fallback if no tests parsed
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
                error_message = output[-1000:] if has_error else None,
            ))

        return results
    def _url_from_test_name(self, test_name: str, app_name: str) -> str:
        """Guess URL from test name and app name."""
        name = test_name
        for prefix in ["test_"]:
            if name.startswith(prefix):
                name = name[len(prefix):]

        # Remove common action prefixes first
        for prefix in ["get_", "create_", "update_", "delete_", "list_", "post_"]:
            if name.startswith(prefix):
                name = name[len(prefix):]

        # Use app_name if available, otherwise fall back to generic API path
        if app_name:
            # Check if the name already contains the app_name to avoid duplication
            if name.startswith(f"{app_name}_"):
                name = name[len(app_name)+1:]  # Remove "app_" prefix
            return f"/api/{app_name}/{name.replace('_', '/')}/"
        return f"/api/{name.replace('_', '/')}/"
    def _method_from_test_name(self, test_name: str) -> list[str]:
        """Guess HTTP method from test name."""
        name = test_name.lower()
        if "create" in name or "post" in name:   return ["POST"]
        if "update" in name or "put" in name:    return ["PUT"]
        if "delete" in name:                      return ["DELETE"]
        if "patch" in name:                       return ["PATCH"]
        return ["GET"]

    def _extract_actual_code(self, error_msg: str | None) -> int:
        """Extract actual status code from error message."""
        if not error_msg:
            return 200
        # Match pattern like "500 != 200"
        match = re.search(r"(\d{3})\s*!=\s*\d{3}", error_msg)
        if match:
            return int(match.group(1))
        # Look for status code in error response body like {"status":500}
        match = re.search(r'"status":\s*(\d{3})', error_msg)
        if match:
            return int(match.group(1))
        # Look for status codes in messages like "Response Status: 500"
        match = re.search(r"Response Status:\s*(\d{3})", error_msg)
        if match:
            return int(match.group(1))
        # For server errors without explicit codes, default to 500
        if any(keyword in error_msg.lower() for keyword in ["internal server error", "server fault", "server error", "typeerror", "traceback"]):
            return 500
        return 0

    def _extract_expected_code(self, error_msg: str | None) -> int:
        """Extract expected status code from error message."""
        if not error_msg:
            return 200
        # Match pattern like "500 != 200" - we want the second one
        match = re.search(r"\d{3}\s*!=\s*(\d{3})", error_msg)
        if match:
            return int(match.group(1))
        return 200

    def _extract_url_and_methods(self, output: str, test_name: str) -> tuple[str, list[str]]:
        """Extract URL and HTTP methods from test output INFO lines for a specific test."""
        url = ""
        methods = []

        # Look for INFO lines related to this specific test
        # First find the test section, then extract INFO lines within it
        test_section_pattern = re.compile(
            rf"(?:FAIL|ERROR):\s+{re.escape(test_name)}.*?\n(.*?)"
            rf"(?=\n(?:FAIL|ERROR|Ran|OK|\-{{70}}|\n\n|$))",
            re.DOTALL,
        )
        test_match = test_section_pattern.search(output)

        test_content = test_match.group(1) if test_match else output

        # Pattern: INFO Sending Request: POST /api/user/login/
        request_pattern = re.compile(
            r"INFO\s+Sending\s+Request:\s+(POST|GET|PUT|DELETE|PATCH)\s+([^\s\n]+)",
            re.IGNORECASE
        )

        for match in request_pattern.finditer(test_content):
            method = match.group(1).upper()
            extracted_url = match.group(2)
            if method not in methods:
                methods.append(method)
            if not url:  # Take the first URL found as primary
                url = extracted_url

        return url, methods

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
        """Extract detailed error information from test output."""
        # Find the error section for this test
        error_pattern = re.compile(
            rf"(?:FAIL|ERROR):\s+{re.escape(test_name)}.*?\n(.*?)"
            rf"(?=\n(?:FAIL|ERROR|Ran|OK|\-{{70}}|$))",
            re.DOTALL,
        )
        match = error_pattern.search(output)
        if match:
            error_section = match.group(1).strip()
            # Extract the most relevant part - the assertion error or traceback
            # Look for lines with "AssertionError" or the actual error message
            assertion_match = re.search(
                r"(AssertionError:.+?$|TypeError:.+?$|.*?Internal Server Error.+?$)",
                error_section, re.MULTILINE | re.DOTALL
            )
            if assertion_match:
                return assertion_match.group(1).strip()[:1000]
            return error_section[:1000]
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
            timeout=self.ERROR_TIMEOUT,
        )
        console.print("  [green]✓ Dependencies installed[/green]")