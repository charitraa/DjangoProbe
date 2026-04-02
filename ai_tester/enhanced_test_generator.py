import time
from pathlib import Path
from rich.console import Console
from ai_tester.models import EndpointInfo
from ai_tester.ai_helper import AIHelper
from ai_tester.app_analyzer import AppAnalyzer

console = Console()


class EnhancedTestGenerator:
    """
    Enhanced test generator that uses AI-powered app analysis for test generation.

    This module:
    1. Analyzes each Django app deeply using AppAnalyzer
    2. Generates AI-powered prompts based on the analysis
    3. Uses those prompts to generate comprehensive test cases
    4. Processes apps one by one with detailed analysis and reporting

    Usage:
        generator = EnhancedTestGenerator(repo_path, endpoints, analysis)
        test_files = generator.generate()
    """

    MAX_TOKENS = 8000  # Maximum tokens for AI test generation (reduced to stay within 12K TPM limit)

    def __init__(
        self,
        repo_path: str,
        endpoints: list[EndpointInfo],
        analysis=None,  # ProjectAnalysis
    ):
        self.repo_path = Path(repo_path)
        self.endpoints = endpoints
        self.analysis = analysis
        self.output_dir = self.repo_path / "tests" / "generated"
        self.ai_helper = AIHelper(str(self.repo_path), analysis=analysis)
        self.app_analyzer = AppAnalyzer(str(self.repo_path), self.ai_helper)

    # PUBLIC
    def generate(self) -> list[str]:
        """
        Generate test files for all endpoints using AI-powered analysis.

        This processes each app one by one:
        1. Deeply analyze the app using AppAnalyzer
        2. Generate AI-powered prompt based on analysis
        3. Use that prompt to generate comprehensive test cases
        4. Write tests to file
        """
        if not self.endpoints:
            console.print(
                "[yellow]⚠ No endpoints — nothing to generate[/yellow]"
            )
            return []

        self._setup_output_dir()
        app_groups = self._group_by_app()

        console.print(
            f"\n  [dim]Analyzing and generating tests for "
            f"{len(app_groups)} app(s)...[/dim]"
        )

        generated_files: list[str] = []

        for app_name, app_endpoints in app_groups.items():
            file_path = self._generate_for_app(app_name, app_endpoints)
            if file_path:
                generated_files.append(file_path)
            time.sleep(2)  # Brief pause between apps to avoid rate limits

        return generated_files

    # PER-APP GENERATION
    def generate_for_app(
        self,
        app_name: str,
        app_endpoints: list[EndpointInfo],
    ) -> str | None:
        """
        Public method to generate test file for one app using AI-powered analysis.

        Process:
        1. Analyze the app deeply
        2. Generate AI-powered prompt
        3. Use prompt to generate test cases
        4. Write to file
        """

        return self._generate_for_app(app_name, app_endpoints)

    def _generate_for_app(
        self,
        app_name: str,
        app_endpoints: list[EndpointInfo],
    ) -> str | None:
        """
        Generate test file for one app using AI-powered analysis.

        Process:
        1. Analyze the app deeply
        2. Generate AI-powered prompt
        3. Use prompt to generate test cases
        4. Write to file
        """
        console.print(
            f"\n  [bold cyan]{'='*60}[/bold cyan]"
        )
        console.print(
            f"  [bold cyan]Processing App:[/bold cyan] [green]{app_name}[/green] "
            f"[dim]({len(app_endpoints)} endpoints)[/dim]"
        )
        console.print(
            f"  [bold cyan]{'='*60}[/bold cyan]"
        )

        file_path = self.output_dir / f"test_{app_name}.py"

        # Step 1: Deeply analyze the app
        structured_analysis, ai_prompt = self.app_analyzer.analyze_app(
            app_name, app_endpoints
        )

        if not ai_prompt:
            console.print(
                f"  [red]✗ Failed to analyze and generate prompt for {app_name}[/red]"
            )
            return None

        # Step 2: Use AI prompt to generate test cases
        console.print(f"\n  [dim]→ Generating test cases using AI prompt...[/dim]")
        content = self._generate_tests_with_ai_prompt(
            app_name, app_endpoints, ai_prompt, structured_analysis
        )

        if not content:
            console.print(
                f"  [red]✗ Failed to generate tests for {app_name}[/red]"
            )
            return None

        content = self._clean_code(content)

        # Step 3: Write to file
        written = self._write_test_file(app_name, content, file_path)
        return written

    def _generate_tests_with_ai_prompt(
        self,
        app_name: str,
        app_endpoints: list[EndpointInfo],
        ai_prompt: str,
        structured_analysis: dict,
    ) -> str | None:
        """
        Generate test cases using the AI-generated prompt.

        This combines the AI prompt with project context and endpoint information
        to generate comprehensive test cases.
        """
        # Build the system prompt
        system_prompt = """You are an expert Django and DRF test engineer. You write clean, realistic, well-documented Django TestCase code.

Your task:
1. Read the detailed analysis prompt provided
2. Generate complete, comprehensive test cases for all endpoints
3. Follow all instructions in the analysis prompt exactly
4. Include proper setup, authentication, and assertions
5. Test both success and failure cases
6. Include edge cases and validation testing

Return ONLY valid Python code — no markdown fences, no explanation, no preamble. Code must be directly writable to a .py file and executable."""

        # Build the user prompt with the AI-generated analysis
        user_prompt = f"""Generate Django test cases for the "{app_name}" app.

## Detailed Analysis and Instructions:
{ai_prompt}

## Additional Project Context:
"""

        # Add auth information if available
        if self.analysis:
            user_prompt += f"""
- Auth type: {self.analysis.auth_type}
- Login URL: {self.analysis.login_url}
- Auth module: {self.analysis.auth_module}
- Safe User fields: {', '.join(self.analysis.safe_user_fields)}
"""

        # Add endpoint list
        user_prompt += "\n## Endpoints to Test:\n"
        for ep in app_endpoints:
            auth_status = "[REQUIRES AUTH]" if ep.requires_auth else "[PUBLIC]"
            user_prompt += f"- {', '.join(ep.http_methods)} {ep.url_pattern} {auth_status}\n"

        # Add import guidance
        user_prompt += """
## Import Guidelines:
- Use: `from django.test import TestCase, Client`
- Use: `import json`
- Import models from the app's models module (not relative imports)
- DO NOT use relative imports like `from .models import ...`
- DO NOT import serializers or services in tests

## Test Structure Guidelines:
1. Create a test class that inherits from TestCase
2. Implement setUp() method with authentication setup
3. Create separate test methods for each endpoint and HTTP method
4. Include meaningful test method names (e.g., test_create_user_success, test_get_list_unauthorized)
5. Use assertEqual, assertIn, assertTrue with descriptive messages
6. Include both success and failure test cases

## Response Codes:
- 200: GET success
- 201: POST success (created)
- 204: DELETE success
- 400: Bad request (validation error)
- 401: Unauthorized
- 403: Forbidden
- 404: Not found
- 405: Method not allowed

Generate the complete test file now."""

        console.print(f"    [dim]Calling AI model...[/dim]")
        response = self.ai_helper.call_with_retry(
            model=self.ai_helper.MODEL,
            max_tokens=self.MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        if response:
            content = response.choices[0].message.content
            if content:
                console.print(
                    f"    [green]✓ Generated {len(content)} chars of test code[/green]"
                )
                return content
        else:
            console.print(f"    [red]✗ AI generation failed after retries[/red]")

        return None

    # FILE WRITING
    def _write_test_file(
        self,
        app_name: str,
        content: str,
        file_path: Path,
    ) -> str:
        """Write test file to disk with backup support."""

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")

            # Same content — skip silently
            if existing.strip() == content.strip():
                console.print(
                    f"  [dim]↔ No changes:[/dim] test_{app_name}.py"
                )
                return str(file_path)

            # Different — tell user + backup
            console.print(
                f"  [yellow]⚠ Existing test found for:[/yellow] {app_name}"
            )

            backup_path = self._backup_file(app_name, existing)

            console.print(
                f"  [yellow]↺ Old version backed up →[/yellow] "
                f"tests/generated/backup/{backup_path.name}"
            )
            console.print(
                f"  [dim]Writing new version...[/dim]"
            )

        # Write new content
        file_path.write_text(content, encoding="utf-8")
        console.print(
            f"  [green]✓ Written:[/green] tests/generated/test_{app_name}.py"
        )

        return str(file_path)

    def _backup_file(self, app_name: str, content: str) -> Path:
        """Backup existing file with timestamp."""
        from datetime import datetime

        backup_dir = self.output_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"test_{app_name}_{timestamp}.py"
        backup_path.write_text(content, encoding="utf-8")

        return backup_path

    # SETUP
    def _setup_output_dir(self) -> None:
        """Create output directory and __init__.py files."""

        self.output_dir.mkdir(parents=True, exist_ok=True)

        tests_init = self.repo_path / "tests" / "__init__.py"
        if not tests_init.exists():
            tests_init.write_text("# Auto-generated by DjangoProbe\n")

        gen_init = self.output_dir / "__init__.py"
        if not gen_init.exists():
            gen_init.write_text("# Auto-generated by DjangoProbe\n")

    # HELPERS
    def _group_by_app(self) -> dict[str, list[EndpointInfo]]:
        """Group endpoints by app name."""
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


def generate_with_enhanced_analyzer(
    repo_path: str,
    endpoints: list[EndpointInfo],
    analysis=None,
) -> list[str]:
    """
    Convenience function to generate tests with enhanced AI-powered analysis.

    Args:
        repo_path: Path to the Django project
        endpoints: List of discovered endpoints
        analysis: ProjectAnalysis object (optional)

    Returns:
        List of generated test file paths
    """
    generator = EnhancedTestGenerator(
        repo_path=repo_path,
        endpoints=endpoints,
        analysis=analysis,
    )
    return generator.generate()
