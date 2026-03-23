import time
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt

from ai_tester.models import EndpointInfo
from ai_tester.ai_helper import AIHelper

console = Console()


class TestGenerator:
    """
    Generates Django test files for all discovered endpoints.

    Usage:
        generator  = TestGenerator(repo_path, endpoints)
        test_files = generator.generate()
    """

    def __init__(
        self,
        repo_path:  str,
        endpoints:  list[EndpointInfo],
        analysis = None,   # ← ProjectAnalysis
    ):
        self.repo_path  = Path(repo_path)
        self.endpoints  = endpoints
        self.analysis   = analysis
        self.output_dir = self.repo_path / "tests" / "generated"  # ← ADD THIS
        self.ai_helper  = AIHelper(
            str(self.repo_path),
            analysis=analysis
        )

    # ─────────────────────────────────────────
    #  PUBLIC
    # ─────────────────────────────────────────

    def generate(self) -> list[str]:
        """Generate test files for all endpoints."""

        if not self.endpoints:
            console.print(
                "[yellow]⚠ No endpoints — nothing to generate[/yellow]"
            )
            return []

        self._setup_output_dir()
        app_groups = self._group_by_app()

        console.print(
            f"\n  [dim]Generating tests for "
            f"{len(app_groups)} app(s)...[/dim]"
        )

        generated_files: list[str] = []

        for app_name, app_endpoints in app_groups.items():
            file_path = self._generate_for_app(app_name, app_endpoints)
            if file_path:
                generated_files.append(file_path)
            time.sleep(3)

        return generated_files

    # ─────────────────────────────────────────
    #  PER-APP GENERATION
    # ─────────────────────────────────────────

    def _generate_for_app(
        self,
        app_name:      str,
        app_endpoints: list[EndpointInfo],
    ) -> str | None:
        """Generate test file for one app."""

        console.print(
            f"\n  [bold]App:[/bold] [cyan]{app_name}[/cyan] "
            f"[dim]({len(app_endpoints)} endpoints)[/dim]"
        )

        file_path = self.output_dir / f"test_{app_name}.py"

        # ── Generate via AI ────────────────────────
        content = self.ai_helper.generate_tests(app_name, app_endpoints)

        if not content:
            console.print(
                f"  [red]✗ Failed to generate tests for {app_name}[/red]"
            )
            return None

        content = self._clean_code(content)

        # ── Write (with backup if file existed) ────
        written = self._write_test_file(app_name, content, file_path)
        return written
    # ─────────────────────────────────────────
    #  FILE WRITING
    # ─────────────────────────────────────────

    def _write_test_file(
        self,
        app_name:  str,
        content:   str,
        file_path: Path,
    ) -> str:

        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")

            # ── Same content — skip silently ──────
            if existing.strip() == content.strip():
                console.print(
                    f"  [dim]↔ No changes:[/dim] "
                    f"test_{app_name}.py"
                )
                return str(file_path)

            # ── Different — tell user + backup ────
            console.print(
                f"  [yellow]⚠ Existing test found for:[/yellow] "
                f"[cyan]{app_name}[/cyan]"
            )

            backup_path = self._backup_file(app_name, existing)

            console.print(
                f"  [yellow]↺ Old version backed up →[/yellow] "
                f"tests/generated/backup/{backup_path.name}"
            )
            console.print(
                f"  [dim]Writing new version...[/dim]"
            )

        # ── Write new content ─────────────────────
        file_path.write_text(content, encoding="utf-8")
        console.print(
            f"  [green]✓ Written:[/green] "
            f"tests/generated/test_{app_name}.py"
        )

        return str(file_path)
    def _backup_file(self, app_name: str, content: str) -> Path:
        """Backup existing file with timestamp."""
        backup_dir = self.output_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"test_{app_name}_{timestamp}.py"
        backup_path.write_text(content, encoding="utf-8")

        return backup_path

    # ─────────────────────────────────────────
    #  SETUP
    # ─────────────────────────────────────────

    def _setup_output_dir(self) -> None:
        """Create output directory and __init__.py files."""

        self.output_dir.mkdir(parents=True, exist_ok=True)

        tests_init = self.repo_path / "tests" / "__init__.py"
        if not tests_init.exists():
            tests_init.write_text("# Auto-generated by DjangoProbe\n")

        gen_init = self.output_dir / "__init__.py"
        if not gen_init.exists():
            gen_init.write_text("# Auto-generated by DjangoProbe\n")

    # ─────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────

    def _group_by_app(self) -> dict[str, list[EndpointInfo]]:
        groups: dict[str, list[EndpointInfo]] = {}
        for ep in self.endpoints:
            groups.setdefault(ep.app_name, []).append(ep)
        return groups

    def _clean_code(self, content: str) -> str:
        """Remove accidental markdown fences."""
        content = content.strip()
        if content.startswith("```python"):
            content = content[len("```python"):].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        return content