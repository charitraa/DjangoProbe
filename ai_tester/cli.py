import re
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from ai_tester.models import InputType, ProjectSource
from ai_tester.repo_handler import RepoHandler
from ai_tester.endpoint_scanner import EndpointScanner
from ai_tester.test_generator import TestGenerator
from ai_tester.report import ReportGenerator
from ai_tester.project_analyzer import ProjectAnalyzer
from ai_tester.app_test_runner  import AppTestRunner

app = typer.Typer(help="AI-powered Django API test runner")
console = Console()


class InputDetector:
    """Detects and validates user input type."""

    KNOWN_GIT_HOSTS = ["github.com", "gitlab.com", "bitbucket.org"]

    def __init__(self, source: str):
        self.source = source

    def detect(self) -> InputType:
        if self.source.startswith("git@"):
            return InputType.SSH_URL
        if self.source.startswith(("http://", "https://")):
            return InputType.GIT_URL
        if (
            self.source.startswith(("/", "./", "~/", "~\\"))
            or Path(self.source).exists()
        ):
            return InputType.LOCAL
        raise typer.BadParameter(
            f"Cannot detect input type for: '{self.source}'\n"
            "  Expected: a GitHub/GitLab URL, SSH git URL, or local path."
        )

    def validate(self, input_type: InputType) -> None:
        if input_type == InputType.GIT_URL:
            self._validate_git_url()
        elif input_type == InputType.SSH_URL:
            self._validate_ssh_url()
        elif input_type == InputType.LOCAL:
            self._validate_local_path()

    def _validate_git_url(self) -> None:
        pattern = re.compile(
            r"^https?://"
            r"[\w.\-]+"
            r"(/[\w.\-~%+]+)+"
            r"(\.git)?$"
        )
        if not pattern.match(self.source):
            console.print(f"[red]✗ Invalid URL format:[/red] {self.source}")
            raise typer.Exit(code=1)
        if not any(host in self.source for host in self.KNOWN_GIT_HOSTS):
            console.print(
                f"[yellow]⚠ Warning:[/yellow] '{self.source}' is not a known "
                f"git host. Proceeding anyway..."
            )

    def _validate_ssh_url(self) -> None:
        pattern = re.compile(r"^git@[\w.\-]+:[\w.\-]+/[\w.\-]+(\.git)?$")
        if not pattern.match(self.source):
            console.print(
                f"[red]✗ Invalid SSH URL:[/red] {self.source}\n"
                "  Expected format: git@github.com:username/repo.git"
            )
            raise typer.Exit(code=1)

    def _validate_local_path(self) -> None:
        path = Path(self.source).expanduser().resolve()
        if not path.exists():
            console.print(f"[red]✗ Path does not exist:[/red] {path}")
            raise typer.Exit(code=1)
        if not path.is_dir():
            console.print(f"[red]✗ Path is not a folder:[/red] {path}")
            raise typer.Exit(code=1)
        if not (path / "manage.py").exists():
            console.print(
                f"[red]✗ No manage.py found in:[/red] {path}\n"
                "  Make sure you're pointing to the root of a Django project."
            )
            raise typer.Exit(code=1)
        console.print(f"[green]✓ Django project confirmed:[/green] {path}")


@app.command()
def analyze(
    source: str = typer.Argument(
        ...,
        help="GitHub URL, GitLab URL, SSH git URL, or local project path"
    ),
    output: str = typer.Option(
        None, "--output",
        help="Export report (e.g. report.json or report.pdf)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Show detailed logs"
    ),
):
    #Banner
    console.print(Panel(
        "[bold cyan]DjangoProbe[/bold cyan]\n"
        "[dim]Intelligent endpoint testing for Django projects[/dim]",
        border_style="cyan"
    ))

    # Step 1: Detect
    console.print(f"\n[bold]→ Analyzing input:[/bold] {source}")
    detector = InputDetector(source)
    try:
        input_type = detector.detect()
    except typer.BadParameter as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(code=1)
    console.print(f"  [dim]Detected type:[/dim] [cyan]{input_type.value}[/cyan]")

    # Step 2: Validate
    console.print("\n[bold]→ Validating source...[/bold]")
    detector.validate(input_type)
    project = ProjectSource(raw_input=source, input_type=input_type)

    # Module 2: Repo Handler
    # Outside spinner — may prompt user about cache
    console.print("\n[bold]→ Resolving project...[/bold]")
    handler           = RepoHandler(project)
    project.repo_path = handler.resolve()
    console.print(f"[green]✓ Project ready at:[/green] {project.repo_path}")

    # Module 3: Endpoint Scanner
    # Inside spinner — no prompts
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task      = progress.add_task("Scanning endpoints...", total=None)
        scanner   = EndpointScanner(project.repo_path)
        endpoints = scanner.scan()
        progress.remove_task(task)
    console.print(f"[green]✓ Found {len(endpoints)} endpoint(s)[/green]")

    # ── Module 4+5: Per-app loop
    console.print("\n[bold]→ Generating and testing app by app...[/bold]")

    analyzer = ProjectAnalyzer(project.repo_path)
    analysis = analyzer.analyze()
    all_results = []

    # Group endpoints by app
    generator   = TestGenerator(project.repo_path, endpoints, analysis)
    app_groups  = generator._group_by_app()

    runner = AppTestRunner(project.repo_path)

    for app_name, app_endpoints in app_groups.items():

        console.print(
            f"\n[bold cyan]── App: {app_name} ──[/bold cyan]"
        )

        # Step 1 — Generate test into app's own tests.py
        test_file = generator.generate_for_app_inplace(
            app_name, app_endpoints
        )
        if not test_file:
            console.print(f"  [red]✗ Skipping {app_name}[/red]")
            continue

        # Step 2 — Run tests for this app only
        results, run_output = runner.run_single_app(app_name)

        if run_output.startswith("ERROR:"):
            console.print(f"  [red]✗ Runner error:[/red] {run_output}")
            continue
        # Step 3 — Check results
        errors = [r for r in results if r.status in ("ERROR", "FAILED")]

        if not errors:
            console.print(
                f"  [green]✅ {app_name}: All tests passed![/green]"
            )
        else:
            console.print(
                f"  [yellow]⚠ {app_name}: "
                f"{len(errors)} errors — saving to JSON[/yellow]"
            )
            # Save per-app error JSON
            runner.save_app_errors(app_name, errors, run_output)

        all_results.extend(results)

    #Module 6: Report
    report = ReportGenerator(
        all_results,
        output_path = output,
        repo_path   = project.repo_path,
    )
    report.print()


if __name__ == "__main__":
    app()