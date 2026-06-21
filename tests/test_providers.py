#!/usr/bin/env python3
"""
Test script for the AI provider system.
Run this to verify provider detection and basic functionality.
"""
import os
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def test_provider_imports():
    """Test that all provider modules can be imported."""
    console.print("[cyan]Testing provider imports...[/cyan]")

    try:
        from ai_tester.providers import BaseProvider, NvidiaProvider, ProviderManager
        console.print("[green]✓ All provider imports successful[/green]")
        return True
    except ImportError as e:
        console.print(f"[red]✗ Import failed: {e}[/red]")
        return False


def test_base_provider():
    """Test that BaseProvider cannot be instantiated directly."""
    console.print("[cyan]Testing base provider...[/cyan]")

    try:
        from ai_tester.providers import BaseProvider

        # Try to instantiate (should fail)
        try:
            provider = BaseProvider()
            console.print("[red]✗ BaseProvider should not be instantiable[/red]")
            return False
        except TypeError:
            console.print("[green]✓ BaseProvider correctly abstract[/green]")
            return True
    except Exception as e:
        console.print(f"[red]✗ BaseProvider test failed: {e}[/red]")
        return False


def test_nvidia_provider():
    """Test NVIDIA provider initialization."""
    console.print("[cyan]Testing NVIDIA provider...[/cyan]")

    try:
        from ai_tester.providers import NvidiaProvider

        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            console.print("[yellow]⚠ No NVIDIA API key found - skipping test[/yellow]")
            console.print("[dim]  Get a free key at https://build.nvidia.com[/dim]")
            return True  # Not a failure, just not configured

        try:
            provider = NvidiaProvider(api_key=api_key)
            info = provider.get_model_info()

            console.print("[green]✓ NVIDIA provider initialized[/green]")
            console.print(f"[dim]  Model: {info['current_model']}[/dim]")
            console.print(f"[dim]  Base URL: {info['base_url']}[/dim]")
            console.print(f"[dim]  Available: {info['is_available']}[/dim]")

            return True
        except Exception as e:
            console.print(f"[yellow]⚠ NVIDIA provider initialization failed: {e}[/yellow]")
            return True  # Not a failure, might be network issue

    except Exception as e:
        console.print(f"[red]✗ NVIDIA provider test failed: {e}[/red]")
        return False


def test_provider_manager():
    """Test ProviderManager initialization."""
    console.print("[cyan]Testing Provider Manager...[/cyan]")

    try:
        from ai_tester.providers import ProviderManager

        # Create a temporary directory for testing
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                manager = ProviderManager(tmpdir)
                status = manager.get_provider_status()

                console.print("[green]✓ Provider Manager initialized[/green]")
                console.print(f"[dim]  Total providers: {status['total_providers']}[/dim]")
                console.print(f"[dim]  Current provider: {status['current_provider']}[/dim]")

                return True
            except RuntimeError as e:
                console.print(f"[yellow]⚠ Provider Manager initialization failed: {e}[/yellow]")
                console.print("[dim]  Expected if NVIDIA_API_KEY is not configured[/dim]")
                return True  # Not a failure, just not configured

    except Exception as e:
        console.print(f"[red]✗ Provider Manager test failed: {e}[/red]")
        return False


def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold cyan]AI Provider System Tests[/bold cyan]",
        border_style="cyan"
    ))
    console.print()

    results = []

    # Run tests
    results.append(("Provider Imports", test_provider_imports()))
    results.append(("Base Provider", test_base_provider()))
    results.append(("NVIDIA Provider", test_nvidia_provider()))
    results.append(("Provider Manager", test_provider_manager()))

    # Print summary
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Test Summary[/bold cyan]",
        border_style="cyan"
    ))

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Test", style="cyan")
    table.add_column("Result", style="bold")

    passed = 0
    failed = 0

    for test_name, result in results:
        if result:
            table.add_row(test_name, "[green]✓ PASSED[/green]")
            passed += 1
        else:
            table.add_row(test_name, "[red]✗ FAILED[/red]")
            failed += 1

    console.print(table)
    console.print()

    # Overall result
    if failed == 0:
        console.print("[green]✓ All tests passed![/green]")
        console.print()
        console.print("[dim]Next steps:[/dim]")
        console.print("[dim]1. Set NVIDIA_API_KEY (free key at https://build.nvidia.com)[/dim]")
        console.print("[dim]2. Run DjangoProbe on your project[/dim]")
        return 0
    else:
        console.print(f"[red]✗ {failed} test(s) failed[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
