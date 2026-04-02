#!/usr/bin/env python3
"""
Demonstration script for using DjangoProbe Enhanced Mode.

This script shows how to programmatically use the enhanced AI-powered
test generation features of DjangoProbe.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_tester.endpoint_scanner import EndpointScanner
from ai_tester.project_analyzer import ProjectAnalyzer
from ai_tester.enhanced_test_generator import EnhancedTestGenerator


def demonstrate_enhanced_mode(project_path: str):
    """
    Demonstrate the enhanced AI-powered test generation.

    Args:
        project_path: Path to the Django project to analyze and test
    """
    print("=" * 70)
    print("DjangoProbe Enhanced Mode Demonstration")
    print("=" * 70)
    print(f"\nProject: {project_path}\n")

    # Step 1: Scan endpoints
    print("Step 1: Scanning endpoints...")
    scanner = EndpointScanner(project_path)
    endpoints = scanner.scan()
    print(f"✓ Found {len(endpoints)} endpoints\n")

    if not endpoints:
        print("No endpoints found. Exiting.")
        return

    # Step 2: Analyze project globally
    print("Step 2: Analyzing project structure...")
    analyzer = ProjectAnalyzer(project_path)
    analysis = analyzer.analyze()
    print("✓ Project analysis complete\n")

    # Step 3: Generate tests using enhanced mode
    print("Step 3: Generating tests with AI-powered analysis...")
    generator = EnhancedTestGenerator(
        repo_path=project_path,
        endpoints=endpoints,
        analysis=analysis,
    )

    test_files = generator.generate()

    print(f"\n✓ Generated {len(test_files)} test file(s):")
    for test_file in test_files:
        print(f"  - {test_file}")

    print("\n" + "=" * 70)
    print("Enhanced Mode Demo Complete!")
    print("=" * 70)
    print("\nGenerated tests are located in: tests/generated/")
    print("Run them with: python manage.py test tests.generated")


def demonstrate_single_app_analysis(project_path: str, app_name: str):
    """
    Demonstrate analyzing and testing a single app.

    Args:
        project_path: Path to the Django project
        app_name: Name of the Django app to analyze
    """
    print("=" * 70)
    print(f"Single App Analysis: {app_name}")
    print("=" * 70)
    print(f"\nProject: {project_path}\n")

    # Import required components
    from ai_tester.ai_helper import AIHelper
    from ai_tester.app_analyzer import AppAnalyzer
    from ai_tester.models import EndpointInfo

    # Create AI helper
    ai_helper = AIHelper(project_path)

    # Create app analyzer
    app_analyzer = AppAnalyzer(project_path, ai_helper)

    # Create sample endpoints (in real use, these come from EndpointScanner)
    sample_endpoints = [
        EndpointInfo(
            url_pattern=f"/api/{app_name}/",
            http_methods=["GET", "POST"],
            view_name=f"{app_name.capitalize()}ViewSet",
            requires_auth=True,
            app_name=app_name,
        ),
    ]

    # Analyze the app
    print(f"Analyzing app: {app_name}...")
    structured_analysis, ai_prompt = app_analyzer.analyze_app(
        app_name, sample_endpoints
    )

    if ai_prompt:
        print(f"✓ Analysis complete!")
        print(f"✓ AI prompt generated ({len(ai_prompt)} characters)")
        print(f"\n=== Structured Analysis ===")
        print(f"Models: {len(structured_analysis.get('models', []))}")
        print(f"Serializers: {len(structured_analysis.get('serializers', []))}")
        print(f"Views: {len(structured_analysis.get('views', []))}")
        print(f"Endpoints: {len(structured_analysis.get('endpoints', []))}")

        print(f"\n=== AI Prompt Preview ===")
        print(ai_prompt[:500] + "..." if len(ai_prompt) > 500 else ai_prompt)
    else:
        print("✗ Analysis failed")


def main():
    """Main entry point for demonstrations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="DjangoProbe Enhanced Mode Demonstration"
    )
    parser.add_argument(
        "project_path",
        help="Path to the Django project to analyze"
    )
    parser.add_argument(
        "--app",
        help="Analyze a single app only",
        default=None,
    )

    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()

    if not project_path.exists():
        print(f"Error: Project path does not exist: {project_path}")
        sys.exit(1)

    if not (project_path / "manage.py").exists():
        print(f"Error: manage.py not found in: {project_path}")
        print("Please provide a valid Django project root directory.")
        sys.exit(1)

    if args.app:
        demonstrate_single_app_analysis(str(project_path), args.app)
    else:
        demonstrate_enhanced_mode(str(project_path))


if __name__ == "__main__":
    main()
