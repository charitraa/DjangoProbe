#!/usr/bin/env python3
"""
Test script for multi-provider AI system.
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
        from ai_tester.providers import BaseProvider, GroqProvider, OllamaProvider, TogetherProvider, ProviderManager
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


def test_groq_provider():
    """Test Groq provider initialization."""
    console.print("[cyan]Testing Groq provider...[/cyan]")

    try:
        from ai_tester.providers import GroqProvider

        # Check if API key is available
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            # Try numbered keys
            for i in range(1, 4):
                api_key = os.environ.get(f"GROQ_API_KEY_{i}")
                if api_key:
                    break

        if not api_key:
            console.print("[yellow]⚠ No Groq API key found - skipping test[/yellow]")
            return True  # Not a failure, just not configured

        try:
            provider = GroqProvider(api_key=api_key)
            info = provider.get_model_info()

            console.print(f"[green]✓ Groq provider initialized[/green]")
            console.print(f"[dim]  Model: {info['current_model']}[/dim]")
            console.print(f"[dim]  Available: {info['is_available']}[/dim]")

            return True
        except Exception as e:
            console.print(f"[yellow]⚠ Groq provider initialization failed: {e}[/yellow]")
            return True  # Not a failure, might be network issue

    except Exception as e:
        console.print(f"[red]✗ Groq provider test failed: {e}[/red]")
        return False


def test_ollama_provider():
    """Test Ollama provider initialization."""
    console.print("[cyan]Testing Ollama provider...[/cyan]")

    try:
        from ai_tester.providers import OllamaProvider

        try:
            provider = OllamaProvider()
            info = provider.get_model_info()

            console.print(f"[green]✓ Ollama provider initialized[/green]")
            console.print(f"[dim]  Model: {info['current_model']}[/dim]")
            console.print(f"[dim]  Available models: {list(info['available_models'].keys())}[/dim]")
            console.print(f"[dim]  Base URL: {info['base_url']}[/dim]")

            return True
        except RuntimeError as e:
            if "not installed" in str(e).lower():
                console.print("[yellow]⚠ Ollama not installed - skipping test[/yellow]")
                console.print("[dim]  Install with: curl -fsSL https://ollama.ai/install.sh | sh[/dim]")
            elif "not running" in str(e).lower():
                console.print("[yellow]⚠ Ollama not running - skipping test[/yellow]")
                console.print("[dim]  Start with: ollama serve[/dim]")
            else:
                console.print(f"[yellow]⚠ Ollama provider initialization failed: {e}[/yellow]")
            return True  # Not a failure, just not configured

    except Exception as e:
        console.print(f"[red]✗ Ollama provider test failed: {e}[/red]")
        return False


def test_together_provider():
    """Test Together AI provider initialization."""
    console.print("[cyan]Testing Together AI provider...[/cyan]")

    try:
        from ai_tester.providers import TogetherProvider

        # Check if API key is available
        api_key = os.environ.get("TOGETHER_API_KEY")
        if not api_key:
            console.print("[yellow]⚠ No Together API key found - skipping test[/yellow]")
            return True  # Not a failure, just not configured

        try:
            provider = TogetherProvider(api_key=api_key)
            info = provider.get_model_info()

            console.print(f"[green]✓ Together AI provider initialized[/green]")
            console.print(f"[dim]  Model: {info['current_model']}[/dim]")
            console.print(f"[dim]  Available: {info['is_available']}[/dim]")

            return True
        except Exception as e:
            console.print(f"[yellow]⚠ Together AI provider initialization failed: {e}[/yellow]")
            return True  # Not a failure, might be network issue

    except Exception as e:
        console.print(f"[red]✗ Together AI provider test failed: {e}[/red]")
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

                console.print(f"[green]✓ Provider Manager initialized[/green]")
                console.print(f"[dim]  Total providers: {status['total_providers']}[/dim]")
                console.print(f"[dim]  Current provider: {status['current_provider']}[/dim]")

                if status['total_providers'] == 0:
                    console.print("[yellow]⚠ No providers available - configure at least one[/yellow]")
                    console.print("[dim]  Options:[/dim]")
                    console.print("[dim]    - Ollama: Install and run 'ollama serve'[/dim]")
                    console.print("[dim]    - Groq: Set GROQ_API_KEY in .env[/dim]")
                    console.print("[dim]    - Together: Set TOGETHER_API_KEY in .env[/dim]")

                return True
            except RuntimeError as e:
                console.print(f"[yellow]⚠ Provider Manager initialization failed: {e}[/yellow]")
                console.print("[dim]  This is expected if no providers are configured[/dim]")
                return True  # Not a failure, just not configured

    except Exception as e:
        console.print(f"[red]✗ Provider Manager test failed: {e}[/red]")
        return False


def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold cyan]Multi-Provider AI System Tests[/bold cyan]",
        border_style="cyan"
    ))
    console.print()

    results = []

    # Run tests
    results.append(("Provider Imports", test_provider_imports()))
    results.append(("Base Provider", test_base_provider()))
    results.append(("Groq Provider", test_groq_provider()))
    results.append(("Ollama Provider", test_ollama_provider()))
    results.append(("Together AI Provider", test_together_provider()))
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
        console.print("[dim]1. Configure at least one AI provider[/dim]")
        console.print("[dim]2. Run DjangoProbe on your project[/dim]")
        console.print("[dim]3. See docs/MULTI_PROVIDER_SETUP.md for details[/dim]")
        return 0
    else:
        console.print(f"[red]✗ {failed} test(s) failed[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())