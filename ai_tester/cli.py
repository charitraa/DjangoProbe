import sys
import re
from pathlib import Path
from enum import Enum

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ai_tester.models import InputType, ProjectSource

# ── will be implemented in later modules ──────────────────────
from ai_tester import repo_handler
from ai_tester import endpoint_scanner
from ai_tester import test_generator
from ai_tester import test_runner
from ai_tester import report
# ──────────────────────────────────────────────────────────────

app     = typer.Typer(help="AI-powered Django API test runner")
console = Console()


# ─────────────────────────────────────────────
#  INPUT TYPE DETECTION
# ─────────────────────────────────────────────

def detect_input_type(source: str) -> InputType:
    """Detect whether the source is a git URL, SSH URL, or local path."""

    if source.startswith("git@"):
        return InputType.SSH_URL

    if source.startswith("http://") or source.startswith("https://"):
        return InputType.GIT_URL

    if (
        source.startswith("/")
        or source.startswith("./")
        or source.startswith("~/")
        or source.startswith("~\\")
        or Path(source).exists()  # catches relative paths like "my-project"
    ):
        return InputType.LOCAL

    raise typer.BadParameter(
        f"Cannot detect input type for: '{source}'\n"
        "  Expected: a GitHub/GitLab URL, SSH git URL, or a local folder path."
    )


# ─────────────────────────────────────────────
#  VALIDATORS
# ─────────────────────────────────────────────

KNOWN_GIT_HOSTS = ["github.com", "gitlab.com", "bitbucket.org"]

def validate_git_url(url: str) -> None:
    """Validate a remote HTTP/HTTPS git URL."""

    # Must be a plausible URL
    pattern = re.compile(
        r"^https?://"           # http or https
        r"[\w.\-]+"             # host (e.g. github.com)
        r"(/[\w.\-~%+]+)+"      # path segments
        r"(\.git)?$"            # optional .git suffix
    )
    if not pattern.match(url):
        console.print(
            f"[red]✗ Invalid URL format:[/red] {url}"
        )
        raise typer.Exit(code=1)

    # Warn if not a known git host (but don't block — could be self-hosted)
    if not any(host in url for host in KNOWN_GIT_HOSTS):
        console.print(
            f"[yellow]⚠ Warning:[/yellow] '{url}' is not a known git host "
            f"(GitHub / GitLab / Bitbucket). Proceeding anyway..."
        )


def validate_ssh_url(url: str) -> None:
    """Validate SSH git URLs like git@github.com:user/repo.git"""

    pattern = re.compile(r"^git@[\w.\-]+:[\w.\-]+/[\w.\-]+(\.git)?$")
    if not pattern.match(url):
        console.print(
            f"[red]✗ Invalid SSH URL:[/red] {url}\n"
            "  Expected format: git@github.com:username/repo.git"
        )
        raise typer.Exit(code=1)


def validate_local_path(path_str: str) -> None:
    """Validate a local folder path is a Django project."""

    path = Path(path_str).expanduser().resolve()

    if not path.exists():
        console.print(
            f"[red]✗ Path does not exist:[/red] {path}"
        )
        raise typer.Exit(code=1)

    if not path.is_dir():
        console.print(
            f"[red]✗ Path is not a folder:[/red] {path}"
        )
        raise typer.Exit(code=1)

    # Check for manage.py — confirms it's a Django project
    manage_py = path / "manage.py"
    if not manage_py.exists():
        console.print(
            f"[red]✗ No manage.py found in:[/red] {path}\n"
            "  Make sure you're pointing to the root of a Django project."
        )
        raise typer.Exit(code=1)

    console.print(f"[green]✓ Django project confirmed:[/green] {path}")


# ─────────────────────────────────────────────
#  MAIN COMMAND
# ─────────────────────────────────────────────

@app.command()
def analyze(
    source: str = typer.Argument(
        ...,
        help="GitHub URL, GitLab URL, SSH git URL, or local project path"
    ),
    ai: bool = typer.Option(
        False,
        "--ai",
        help="Enable AI-assisted test generation"
    ),
    output: str = typer.Option(
        None,
        "--output",
        help="Export report to file (e.g. report.json or report.pdf)"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show detailed logs"
    ),
):
    # ── Banner ────────────────────────────────
    console.print(Panel(
        "[bold cyan]AI Django API Tester[/bold cyan]\n"
        "[dim]Intelligent endpoint testing for Django projects[/dim]",
        border_style="cyan"
    ))

    # ── Step 1: Detect input type ─────────────
    console.print(f"\n[bold]→ Analyzing input:[/bold] {source}")
    try:
        input_type = detect_input_type(source)
    except typer.BadParameter as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(code=1)

    console.print(f"  [dim]Detected type:[/dim] [cyan]{input_type.value}[/cyan]")

    # ── Step 2: Validate ──────────────────────
    console.print("\n[bold]→ Validating source...[/bold]")
    if input_type == InputType.GIT_URL:
        validate_git_url(source)
    elif input_type == InputType.SSH_URL:
        validate_ssh_url(source)
    elif input_type == InputType.LOCAL:
        validate_local_path(source)

    # ── Build ProjectSource object ────────────
    project = ProjectSource(raw_input=source, input_type=input_type)

    # ── Step 3 onwards: Orchestrate modules ──
    # (Each module will be implemented step by step)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # Module 2 — Repo Handler
        task = progress.add_task("Cloning / resolving project...", total=None)
        project.repo_path = repo_handler.resolve(project)
        progress.remove_task(task)
        console.print(f"[green]✓ Project ready at:[/green] {project.repo_path}")

        # Module 3 — Endpoint Scanner
        task = progress.add_task("Scanning endpoints...", total=None)
        endpoints = endpoint_scanner.scan(project.repo_path)
        progress.remove_task(task)
        console.print(f"[green]✓ Found {len(endpoints)} endpoint(s)[/green]")

        # Module 4 — Test Generator
        task = progress.add_task("Generating test cases...", total=None)
        test_files = test_generator.generate(
            project.repo_path, endpoints, use_ai=ai
        )
        progress.remove_task(task)
        console.print(f"[green]✓ Generated {len(test_files)} test file(s)[/green]")

        # Module 5 — Test Runner
        task = progress.add_task("Running tests...", total=None)
        results = test_runner.run(project.repo_path, test_files)
        progress.remove_task(task)
        console.print(f"[green]✓ Tests complete[/green]")

    # Module 6 — Report
    report.print_report(results, output_path=output)


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app()