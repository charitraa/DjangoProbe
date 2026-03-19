import shutil
import re
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from git import Repo, GitCommandError

from ai_tester.models import ProjectSource, InputType

console = Console()
# path to store cloned repos
CACHE_DIR = Path.home() / ".djangoprobe" / "cache"


#  MAIN ENTRY
def resolve(project: ProjectSource) -> str:
    """
    Resolve a project source to a local path.
    """
    if project.input_type == InputType.LOCAL:
        return _resolve_local(project.raw_input)

    elif project.input_type in (InputType.GIT_URL, InputType.SSH_URL):
        return _resolve_remote(project.raw_input)

    else:
        raise ValueError(f"Unknown input type: {project.input_type}")

#  LOCAL PATH HANDLER

def _resolve_local(path_str: str) -> str:
    """
    Copy local Django project into cache.
    Work on the copy — original is never touched.
    """
    source_path = Path(path_str).expanduser().resolve()

    # Validate source
    if not source_path.exists():
        console.print(f"[red]✗ Path not found:[/red] {source_path}")
        raise SystemExit(1)

    if not (source_path / "manage.py").exists():
        console.print(
            f"[red]✗ No manage.py found in:[/red] {source_path}\n"
            "  Not a valid Django project root."
        )
        raise SystemExit(1)

    # Copy into cache
    folder_name = source_path.name
    cache_path  = CACHE_DIR / folder_name

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # If already cached, remove and re-copy (always fresh for local)
    if cache_path.exists():
        console.print(f"  [dim]Refreshing local cache for:[/dim] {folder_name}")
        shutil.rmtree(cache_path)

    console.print(f"  [dim]Copying project to cache...[/dim]")

    try:
        shutil.copytree(
            src=str(source_path),
            dst=str(cache_path),
            ignore=shutil.ignore_patterns(
                # Skip these — no need to copy
                "__pycache__",
                "*.pyc",
                ".git",
                "venv",
                "env",
                ".env",
                "node_modules",
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


#  REMOTE URL HANDLER

def _resolve_remote(url: str) -> str:
    """Clone a remote git repo or use cached version."""

    repo_name  = _extract_repo_name(url)
    clone_path = CACHE_DIR / repo_name

    # ── Already cached ────────────────────────
    if clone_path.exists() and (clone_path / "manage.py").exists():
        console.print(
            f"  [dim]Using cached repo:[/dim] {clone_path}\n"
            f"  [dim]Tip: delete folder to force fresh clone[/dim]"
        )
        return str(clone_path)

    # ── Fresh clone ───────────────────────────
    console.print(f"  [dim]Cloning into:[/dim] {clone_path}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        Repo.clone_from(url, str(clone_path))
        console.print("  [green]✓ Clone successful[/green]")

    except GitCommandError as e:
        error_msg = str(e).lower()

        # ── Handle private repo / auth failure ─
        if any(word in error_msg for word in [
            "authentication", "auth", "permission",
            "access denied", "could not read"
        ]):
            _show_ssh_help(url)

        else:
            console.print(f"[red]✗ Clone failed:[/red] {e}")

        # Clean up partial clone
        if clone_path.exists():
            shutil.rmtree(clone_path)
            console.print("  [dim]Cleaned up partial clone[/dim]")

        raise SystemExit(1)

    # ── Verify Django project ─────────────────
    if not (clone_path / "manage.py").exists():
        console.print(
            "[red]✗ Cloned repo has no manage.py[/red]\n"
            "  This does not appear to be a Django project."
        )
        shutil.rmtree(clone_path)
        raise SystemExit(1)

    console.print("  [green]✓ Django project confirmed[/green]")
    return str(clone_path)


#  SSH HELP MESSAGE

def _show_ssh_help(url: str) -> None:
    """
    Show a clear, helpful message when a private repo
    fails due to authentication.
    """

    # Convert HTTPS url to SSH equivalent for display
    ssh_equivalent = _https_to_ssh(url)

    console.print(Panel(
        "[bold red]✗ Repository is private or access was denied[/bold red]\n\n"

        "[bold white]You have two options:[/bold white]\n\n"

        "[bold cyan]Option 1 — Make the repo public[/bold cyan]\n"
        "  Go to GitHub/GitLab → Settings → Change visibility → Public\n\n"

        "[bold cyan]Option 2 — Set up SSH on this machine[/bold cyan]\n\n"

        "  [bold]Step 1:[/bold] Generate SSH key\n"
        "  [green]$ ssh-keygen -t ed25519 -C \"your@email.com\"[/green]\n\n"

        "  [bold]Step 2:[/bold] Copy your public key\n"
        "  [green]$ cat ~/.ssh/id_ed25519.pub[/green]\n\n"

        "  [bold]Step 3:[/bold] Add it to GitHub\n"
        "  [dim]GitHub → Settings → SSH Keys → New SSH Key → Paste[/dim]\n\n"

        "  [bold]Step 4:[/bold] Test connection\n"
        "  [green]$ ssh -T git@github.com[/green]\n\n"

        "  [bold]Step 5:[/bold] Use SSH URL instead\n"
        f"  [green]$ djangoprobe {ssh_equivalent}[/green]\n\n"

        "[dim]Full guide: https://docs.github.com/en/authentication/connecting-to-github-with-ssh[/dim]",

        title="[bold]Authentication Failed[/bold]",
        border_style="red"
    ))


def _https_to_ssh(url: str) -> str:
    """
    Convert HTTPS GitHub URL to SSH format.
    https://github.com/user/repo  →  git@github.com:user/repo.git
    """
    try:
        # Remove https://
        url = url.replace("https://", "").replace("http://", "")
        # Split host and path
        parts  = url.split("/", 1)
        host   = parts[0]   # e.g. github.com
        path   = parts[1]   # e.g. user/repo
        path   = path.rstrip("/").removesuffix(".git")
        return f"git@{host}:{path}.git"
    except Exception:
        return "git@github.com:username/repo.git"


#  HELPER

def _extract_repo_name(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    repo_name = url.split("/")[-1]
    if ":" in repo_name:
        repo_name = repo_name.split(":")[-1]
    repo_name = re.sub(r"[^\w\-]", "_", repo_name)
    return repo_name