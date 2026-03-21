import os
import re
import sys
import venv
import subprocess
from pathlib import Path
from rich.console import Console
from ai_tester.models import TestResult, EndpointInfo

console = Console()


class TestRunner:
    """
    Runs generated Django tests in an isolated environment.

    Process:
      1. Creates a fresh venv inside the cached repo
      2. Installs project dependencies
      3. Runs tests via: python manage.py test tests.generated
      4. Parses results into TestResult objects

    Usage:
        runner  = TestRunner(repo_path, test_files)
        results = runner.run()
    """

    VENV_DIR = ".probe_venv"

    def __init__(self, repo_path: str, test_files: list[str]):
        self.repo_path  = Path(repo_path)
        self.test_files = test_files
        self.venv_path  = self.repo_path / self.VENV_DIR
        self.python     = self._get_python_path()

    # ─────────────────────────────────────────
    #  PUBLIC — main entry
    # ─────────────────────────────────────────

    def run(self) -> list[TestResult]:
        """
        Run all generated tests.
        Returns list of TestResult objects.
        """

        if not self.test_files:
            console.print(
                "[yellow]⚠ No test files to run[/yellow]"
            )
            return []

        # Step 1 — Setup venv
        self._setup_venv()

        # Step 2 — Install dependencies
        success = self._install_dependencies()
        if not success:
            console.print(
                "[red]✗ Failed to install dependencies[/red]"
            )
            return []

        # Step 3 — Run tests
        output = self._run_tests()

        # Step 4 — Parse results
        results = self._parse_results(output)

        return results

    # ─────────────────────────────────────────
    #  VENV SETUP
    # ─────────────────────────────────────────

    def _setup_venv(self) -> None:
        """Create isolated venv if it doesn't exist."""

        if self.venv_path.exists():
            console.print(
                f"  [dim]Using existing venv:[/dim] {self.VENV_DIR}"
            )
            return

        console.print(
            f"  [dim]Creating isolated venv:[/dim] {self.VENV_DIR}"
        )

        try:
            venv.create(
                str(self.venv_path),
                with_pip   = True,
                clear      = True,
            )
            console.print("  [green]✓ Venv created[/green]")
        except Exception as e:
            console.print(f"[red]✗ Failed to create venv:[/red] {e}")
            raise SystemExit(1)

    def _get_python_path(self) -> Path:
        """Get path to Python executable in venv."""
        if sys.platform == "win32":
            return self.venv_path / "Scripts" / "python.exe"
        return self.venv_path / "bin" / "python"

    # ─────────────────────────────────────────
    #  DEPENDENCY INSTALLATION
    # ─────────────────────────────────────────

    def _install_dependencies(self) -> bool:
        """
        Install project dependencies into venv.
        Reads requirements.txt from repo root.
        """

        req_file = self.repo_path / "requirements.txt"

        if not req_file.exists():
            console.print(
                "[yellow]⚠ No requirements.txt found — "
                "skipping dependency install[/yellow]"
            )
            return True

        console.print("  [dim]Installing dependencies...[/dim]")

        try:
            result = subprocess.run(
                [
                    str(self.python), "-m", "pip",
                    "install", "-r", str(req_file),
                    "--quiet",
                    "--disable-pip-version-check",
                ],
                cwd     = str(self.repo_path),
                capture_output = True,
                text    = True,
                timeout = 300,  # 5 minutes max
            )

            if result.returncode == 0:
                console.print(
                    "  [green]✓ Dependencies installed[/green]"
                )
                return True
            else:
                console.print(
                    f"[red]✗ Dependency install failed:[/red]\n"
                    f"{result.stderr[:500]}"
                )
                return False

        except subprocess.TimeoutExpired:
            console.print(
                "[red]✗ Dependency install timed out (5 min)[/red]"
            )
            return False

        except Exception as e:
            console.print(
                f"[red]✗ Dependency install error:[/red] {e}"
            )
            return False

    # ─────────────────────────────────────────
    #  TEST EXECUTION
    # ─────────────────────────────────────────

    def _run_tests(self) -> str:

        console.print("  [dim]Running tests...[/dim]")

        # Copy current environment + load project .env
        env = os.environ.copy()

        # Load project's .env file into environment
        env_file = self.repo_path / ".env"
        if env_file.exists():
            console.print("  [dim]Loading project .env...[/dim]")
            for line in env_file.read_text().splitlines():
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                # Remove export keyword if present
                if line.startswith("export "):
                    line = line[7:]
                # Parse KEY=VALUE
                if "=" in line:
                    key, _, value = line.partition("=")
                    key   = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env[key] = value

        # Build test labels
        test_labels = []
        for file_path in self.test_files:
            path     = Path(file_path)
            repo_rel = path.relative_to(self.repo_path)
            label    = str(repo_rel).replace("/", ".").replace("\\", ".")
            if label.endswith(".py"):
                label = label[:-3]
            test_labels.append(label)

        console.print(
            f"  [dim]Test modules:[/dim] {', '.join(test_labels)}"
        )

        try:
            result = subprocess.run(
                [
                    str(self.python),
                    "manage.py",
                    "test",
                    *test_labels,
                    "--verbosity=2",
                    "--keepdb",
                ],
                cwd            = str(self.repo_path),
                capture_output = True,
                text           = True,
                timeout        = 300,
                env            = env,
            )

            output = result.stderr + "\n" + result.stdout
            console.print(f"  [dim]Return code:[/dim] {result.returncode}")
            return output

        except subprocess.TimeoutExpired:
            return "ERROR: Test run timed out after 5 minutes"
        except Exception as e:
            return f"ERROR: {e}"
        # ─────────────────────────────────────────
    #  RESULT PARSING
    # ─────────────────────────────────────────

    def _parse_results(self, output: str) -> list[TestResult]:
        """
        Parse Django test output into TestResult objects.

        Django verbosity=2 output looks like:
          test_user_login_post_success (tests.generated.test_user.UserAppTests) ... ok
          test_user_login_post_empty_body (tests.generated.test_user.UserAppTests) ... FAIL
          test_user_me_without_auth (tests.generated.test_user.UserAppTests) ... ERROR
        """

        results: list[TestResult] = []

        # Print raw output summary
        self._print_raw_summary(output)

        # Pattern: test_name (module.Class) ... ok/FAIL/ERROR
        pattern = re.compile(
            r"^(test\w+)\s+\([\w.]+\)\s+\.\.\.\s+(ok|FAIL|ERROR|skip)",
            re.MULTILINE | re.IGNORECASE,
        )

        for match in pattern.finditer(output):
            test_name = match.group(1)
            status    = match.group(2).upper()

            # Map Django status to our status
            status_map = {
                "OK":    "PASSED",
                "FAIL":  "FAILED",
                "ERROR": "ERROR",
                "SKIP":  "SKIPPED",
            }

            # Create a minimal EndpointInfo from test name
            # test_user_create_post_success → /user/create/
            url_pattern = self._url_from_test_name(test_name)

            result = TestResult(
                endpoint      = EndpointInfo(
                    url_pattern   = url_pattern,
                    http_methods  = [],
                    view_name     = "",
                    requires_auth = False,
                    app_name      = "",
                ),
                status        = status_map.get(status, "ERROR"),
                response_code = 0,
                expected_code = 0,
                error_message = self._extract_error(output, test_name),
            )
            results.append(result)

        # If no results parsed — return summary result
        if not results:
            results.append(self._make_summary_result(output))

        return results

    def _print_raw_summary(self, output: str) -> None:
        """Print a clean summary from Django test output."""

        lines = output.strip().split("\n")

        # Find the summary line: "Ran X tests in Ys"
        for line in lines:
            if line.startswith("Ran "):
                console.print(f"  [dim]{line}[/dim]")

        # Find OK / FAILED line
        for line in lines:
            if line.startswith("OK") or line.startswith("FAILED"):
                if "FAILED" in line:
                    console.print(f"  [red]{line}[/red]")
                else:
                    console.print(f"  [green]{line}[/green]")

    def _extract_error(self, output: str, test_name: str) -> str | None:
        """Extract error message for a specific failed test."""

        # Look for FAIL: test_name or ERROR: test_name blocks
        pattern = re.compile(
            rf"(?:FAIL|ERROR):\s+{re.escape(test_name)}.*?\n(.*?)(?=\n(?:FAIL|ERROR|OK|Ran|\-{{70}}))",
            re.DOTALL,
        )
        match = pattern.search(output)
        if match:
            return match.group(1).strip()[:500]  # limit length
        return None

    def _url_from_test_name(self, test_name: str) -> str:
        """
        Guess URL from test name.
        test_user_create_post_success → /user/create/
        """
        # Remove common suffixes
        for suffix in [
            "_post_success", "_get_success", "_put_success",
            "_patch_success", "_delete_success",
            "_post_empty_body_returns_400", "_returns_400",
            "_without_auth_returns_401", "_returns_401",
            "_wrong_method_returns_405", "_returns_405",
            "_with_auth",
        ]:
            test_name = test_name.replace(suffix, "")

        # Remove test_ prefix
        if test_name.startswith("test_"):
            test_name = test_name[5:]

        return "/" + test_name.replace("_", "/") + "/"

    def _make_summary_result(self, output: str) -> TestResult:
        """Fallback result when parsing fails."""

        has_error = "ERROR" in output or "error" in output.lower()
        status    = "ERROR" if has_error else "PASSED"

        return TestResult(
            endpoint      = EndpointInfo(
                url_pattern   = "/",
                http_methods  = [],
                view_name     = "unknown",
                requires_auth = False,
                app_name      = "unknown",
            ),
            status        = status,
            response_code = 0,
            expected_code = 0,
            error_message = output[:500] if has_error else None,
        )