import shutil
import re
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from git import Repo, GitCommandError

from ai_tester.models import ProjectSource, InputType

console   = Console()
CACHE_DIR = Path.home() / ".djangoprobe" / "cache"


class RepoHandler:
    """
    Handles resolving a project source to a local path.

    Supports:
      - Local paths  → copies to cache, works on copy
      - Git URLs     → clones into cache
      - SSH URLs     → clones via SSH into cache

    Usage:
        handler   = RepoHandler(project)
        repo_path = handler.resolve()
    """

    def __init__(self, project: ProjectSource):
        self.project    = project
        self.cache_dir  = CACHE_DIR

    # ─────────────────────────────────────────
    #  PUBLIC — main entry
    # ─────────────────────────────────────────

    def resolve(self) -> str:
        """
        Resolve project source to a local path.
        Returns absolute path string to the working copy.
        """
        if self.project.input_type == InputType.LOCAL:
            return self._resolve_local()

        elif self.project.input_type in (InputType.GIT_URL, InputType.SSH_URL):
            return self._resolve_remote()

        else:
            raise ValueError(
                f"Unknown input type: {self.project.input_type}"
            )

    # ─────────────────────────────────────────
    #  LOCAL PATH HANDLER
    # ─────────────────────────────────────────

    def _resolve_local(self) -> str:
        """
        Copy local Django project into cache.
        Original is NEVER touched — we work on the copy.
        """
        source_path = (
            Path(self.project.raw_input).expanduser().resolve()
        )

        self._validate_django_project(source_path)

        folder_name = source_path.name
        cache_path  = self.cache_dir / folder_name

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Always fresh copy for local projects
        if cache_path.exists():
            console.print(
                f"  [dim]Refreshing local cache for:[/dim] {folder_name}"
            )
            shutil.rmtree(cache_path)

        console.print("  [dim]Copying project to cache...[/dim]")

        try:
            shutil.copytree(
                src    = str(source_path),
                dst    = str(cache_path),
                ignore = shutil.ignore_patterns(
                    "__pycache__", "*.pyc",
                    ".git", "venv", "env",
                    ".env", "node_modules",
                )
            )
        except Exception as e:
            console.print(f"[red]✗ Failed to copy project:[/red] {e}")
            raise SystemExit(1)

        console.print(
            f"  [green]✓ Project copied to cache[/green]\n"
            f"  [dim]Original is untouched:[/dim] {source_path}\n"
            f"  [dim]Working copy:[/dim] {cache_path}"
        )
        return str(cache_path)

    # ─────────────────────────────────────────
    #  REMOTE URL HANDLER
    # ─────────────────────────────────────────

    def _resolve_remote(self) -> str:
        """
        Clone a remote git repo into cache.
        Uses cached version if already cloned.
        """
        url        = self.project.raw_input
        repo_name  = self._extract_repo_name(url)
        clone_path = self.cache_dir / repo_name

        # ── Already cached ────────────────────
        if self._is_valid_cached_project(clone_path):
            console.print(
                f"  [dim]Using cached repo:[/dim] {clone_path}\n"
                f"  [dim]Tip: delete folder to force fresh clone[/dim]"
            )
            return str(clone_path)

        # ── Fresh clone ───────────────────────
        console.print(f"  [dim]Cloning into:[/dim] {clone_path}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            Repo.clone_from(url, str(clone_path))
            console.print("  [green]✓ Clone successful[/green]")

        except GitCommandError as e:
            self._handle_clone_error(e, url, clone_path)

        # ── Verify Django project ─────────────
        if not (clone_path / "manage.py").exists():
            console.print(
                "[red]✗ Cloned repo has no manage.py[/red]\n"
                "  This does not appear to be a Django project."
            )
            shutil.rmtree(clone_path)
            raise SystemExit(1)

        console.print("  [green]✓ Django project confirmed[/green]")
        return str(clone_path)

    # ─────────────────────────────────────────
    #  ERROR HANDLER
    # ─────────────────────────────────────────

    def _handle_clone_error(
        self,
        error:      GitCommandError,
        url:        str,
        clone_path: Path,
    ) -> None:
        """Handle clone failure — shows SSH guide for auth errors."""

        error_msg = str(error).lower()

        auth_keywords = [
            "authentication", "auth",
            "permission", "access denied",
            "could not read",
        ]

        if any(word in error_msg for word in auth_keywords):
            self._show_ssh_help(url)
        else:
            console.print(f"[red]✗ Clone failed:[/red] {error}")

        # Clean up partial clone
        if clone_path.exists():
            shutil.rmtree(clone_path)
            console.print("  [dim]Cleaned up partial clone[/dim]")

        raise SystemExit(1)

    # ─────────────────────────────────────────
    #  SSH HELP MESSAGE
    # ─────────────────────────────────────────

    def _show_ssh_help(self, url: str) -> None:
        """Show step-by-step SSH setup guide for private repos."""

        ssh_equivalent = self._https_to_ssh(url)

        console.print(Panel(
            "[bold red]✗ Repository is private or access was denied"
            "[/bold red]\n\n"

            "[bold white]You have two options:[/bold white]\n\n"

            "[bold cyan]Option 1 — Make the repo public[/bold cyan]\n"
            "  GitHub/GitLab → Settings → Change visibility → Public\n\n"

            "[bold cyan]Option 2 — Set up SSH on this machine[/bold cyan]\n\n"

            "  [bold]Step 1:[/bold] Generate SSH key\n"
            "  [green]$ ssh-keygen -t ed25519 -C \"your@email.com\""
            "[/green]\n\n"

            "  [bold]Step 2:[/bold] Copy your public key\n"
            "  [green]$ cat ~/.ssh/id_ed25519.pub[/green]\n\n"

            "  [bold]Step 3:[/bold] Add it to GitHub\n"
            "  [dim]GitHub → Settings → SSH Keys → New SSH Key"
            " → Paste[/dim]\n\n"

            "  [bold]Step 4:[/bold] Test connection\n"
            "  [green]$ ssh -T git@github.com[/green]\n\n"

            "  [bold]Step 5:[/bold] Re-run with SSH URL\n"
            f"  [green]$ djangoprobe {ssh_equivalent}[/green]\n\n"

            "[dim]Guide: https://docs.github.com/en/authentication"
            "/connecting-to-github-with-ssh[/dim]",

            title  = "[bold]Authentication Failed[/bold]",
            border_style = "red",
        ))

    # ─────────────────────────────────────────
    #  VALIDATORS
    # ─────────────────────────────────────────

    def _validate_django_project(self, path: Path) -> None:
        """Ensure path exists and contains manage.py."""

        if not path.exists():
            console.print(f"[red]✗ Path not found:[/red] {path}")
            raise SystemExit(1)

        if not (path / "manage.py").exists():
            console.print(
                f"[red]✗ No manage.py found in:[/red] {path}\n"
                "  Not a valid Django project root."
            )
            raise SystemExit(1)

    def _is_valid_cached_project(self, path: Path) -> bool:
        """Check if a valid cached Django project already exists."""
        return path.exists() and (path / "manage.py").exists()

    # ─────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────

    def _extract_repo_name(self, url: str) -> str:
        """
        Extract clean repo name from any git URL.

        Examples:
          https://github.com/charitra/my-app      → my-app
          https://github.com/charitra/my-app.git  → my-app
          git@github.com:charitra/my-app.git      → my-app
        """
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        repo_name = url.split("/")[-1]

        # SSH edge case: git@github.com:user/repo
        if ":" in repo_name:
            repo_name = repo_name.split(":")[-1]

        # Sanitize — only safe characters
        return re.sub(r"[^\w\-]", "_", repo_name)

    def _https_to_ssh(self, url: str) -> str:
        """
        Convert HTTPS URL to SSH format for display.
        https://github.com/user/repo → git@github.com:user/repo.git
        """
        try:
            url   = url.replace("https://", "").replace("http://", "")
            parts = url.split("/", 1)
            host  = parts[0]
            path  = parts[1].rstrip("/").removesuffix(".git")
            return f"git@{host}:{path}.git"
        except Exception:
            return "git@github.com:username/repo.git"