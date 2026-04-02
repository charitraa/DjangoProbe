# DjangoProbe

AI-powered Django API test runner that automatically discovers endpoints, generates intelligent test cases, and executes them with detailed reporting.

## Features

- **Automatic Endpoint Discovery**: Scans Django projects to find all API endpoints
- **AI-Powered Test Generation**: Uses Groq API to generate comprehensive test cases
- **Enhanced Mode**: Deep app analysis with AI-generated custom prompts for better test coverage
- **Per-App Testing**: Generates and runs tests for each Django app independently
- **Detailed Reporting**: Provides terminal reports with Rich formatting and JSON exports
- **Multiple Input Sources**: Supports local paths, GitHub, GitLab, and SSH URLs
- **Authentication Detection**: Automatically detects JWT, Token, and Session authentication

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/djangoprobe.git
cd djangoprobe

# Create virtual environment
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### Configuration

Create a `.env` file in your project root:

```env
GROQ_API_KEY_1=gsk_your_first_key_here
GROQ_API_KEY_2=gsk_your_second_key_here  # optional
GROQ_API_KEY_3=gsk_your_third_key_here   # optional
```

Get API keys from: https://console.groq.com/keys

## Usage

### Basic Usage

```bash
# Analyze a local Django project
djangoprobe /path/to/your/django/project

# Analyze a GitHub repository
djangoprobe https://github.com/username/repository

# Analyze a GitLab repository
djangoprobe https://gitlab.com/username/repository

# Analyze using SSH URL
djangoprobe git@github.com:username/repository.git
```

### Enhanced Mode

Use `--enhanced` flag for AI-powered deep app analysis:

```bash
djangoprobe /path/to/project --enhanced

# Short form
djangoprobe /path/to/project -e
```

**Enhanced Mode Benefits:**
- Deep analysis of models, serializers, and views
- AI-generated custom prompts for each app
- Better understanding of relationships and constraints
- More comprehensive test coverage
- App-specific test generation

For detailed information about Enhanced Mode, see [ENHANCED_MODE.md](ENHANCED_MODE.md).

## How It Works

DjangoProbe follows a modular 6-stage pipeline:

### 1. Input Detection & Validation
- Detects input type (local path, GitHub URL, GitLab URL, SSH URL)
- Validates input format and accessibility

### 2. Repository Handling
- Local paths: Copies project to cache directory
- Remote URLs: Clones to cache directory
- Validates Django project presence (manage.py check)

### 3. Endpoint Scanning
- Recursively scans all `urls.py` files
- Detects DRF Routers, ViewSets, APIViews, function-based views
- Returns endpoint information including URL patterns, HTTP methods, auth requirements

### 4. Project Analysis
- Analyzes project ONCE before test generation
- Detects auth type (JWT/Session/Token)
- Finds auth app/module path and login URL
- Discovers safe User model fields (excludes ManyToMany for create_user())
- Identifies roles, FK fields, M2M fields

### 5. Test Generation (Standard Mode)
- Groups endpoints by Django app
- Generates per-app test files using AI via Groq API
- Writes tests to `repo/tests/generated/test_<app_name>.py`
- Uses `AIHelper` for intelligent test case generation

### Test Generation (Enhanced Mode)
- Deeply analyzes each Django app using `AppAnalyzer`
- Generates AI-powered custom prompts based on code analysis
- Examines models, serializers, views, and relationships
- Creates comprehensive test cases with better coverage
- Writes tests to `tests/generated/test_<app_name>.py`

### 6. Test Execution
- Runs tests app-by-app in isolated environment
- Creates `.probe_venv` directory for isolated Python environment
- Executes `python manage.py test <app_name> --keepdb`
- Parses test output into `TestResult` objects
- Saves error JSON files to `~/.djangoprobe/errors/`

### 7. Report Generation
- Generates terminal report with Rich formatting
- Exports JSON report to project root as `djangoprobe_report.json`

## Architecture

```
DjangoProbe/
├── ai_tester/
│   ├── __init__.py                 # Package initialization
│   ├── cli.py                      # Command-line interface
│   ├── endpoint_scanner.py         # Endpoint discovery
│   ├── repo_handler.py             # Repository management
│   ├── project_analyzer.py         # Global project analysis
│   ├── app_analyzer.py             # Enhanced: Deep app analysis
│   ├── test_generator.py           # Standard test generation
│   ├── enhanced_test_generator.py  # Enhanced test generation
│   ├── ai_helper.py               # AI API communication
│   ├── app_test_runner.py         # Test execution
│   ├── report.py                  # Report generation
│   └── models.py                 # Data models
├── examples/
│   └── enhanced_mode_demo.py      # Enhanced mode demo
├── ENHANCED_MODE.md              # Enhanced mode documentation
├── CLAUDE.md                     # Claude Code instructions
└── requirements.txt               # Python dependencies
```

## Data Models

### EndpointInfo
```python
{
    "url_pattern": "/api/user/",
    "http_methods": ["GET", "POST"],
    "view_name": "UserViewSet",
    "requires_auth": True,
    "app_name": "user"
}
```

### TestResult
```python
{
    "endpoint": EndpointInfo,
    "status": "PASSED",  # or "FAILED", "ERROR"
    "response_code": 200,
    "expected_code": 200,
    "error_message": None
}
```

### ProjectAnalysis
```python
{
    "auth_type": "JWT",
    "login_url": "/api/user/login/",
    "auth_module": "apps.user",
    "auth_app_name": "user",
    "safe_user_fields": ["email", "full_name"],
    "roles": ["admin", "teacher", "student"],
    "user_fk_fields": [...],
    "user_m2m_fields": [...]
}
```

## Programmatic Usage

### Standard Mode

```python
from ai_tester import EndpointScanner, ProjectAnalyzer, TestGenerator

# Scan endpoints
scanner = EndpointScanner("/path/to/project")
endpoints = scanner.scan()

# Analyze project
analyzer = ProjectAnalyzer("/path/to/project")
analysis = analyzer.analyze()

# Generate tests
generator = TestGenerator("/path/to/project", endpoints, analysis)
test_files = generator.generate()
```

### Enhanced Mode

```python
from ai_tester import (
    EndpointScanner,
    ProjectAnalyzer,
    EnhancedTestGenerator
)

# Scan endpoints
scanner = EndpointScanner("/path/to/project")
endpoints = scanner.scan()

# Analyze project
analyzer = ProjectAnalyzer("/path/to/project")
analysis = analyzer.analyze()

# Generate tests with enhanced analysis
generator = EnhancedTestGenerator(
    "/path/to/project",
    endpoints,
    analysis
)
test_files = generator.generate()
```

### Single App Analysis

```python
from ai_tester import AIHelper, AppAnalyzer

# Create analyzer
ai_helper = AIHelper("/path/to/project", analysis)
app_analyzer = AppAnalyzer("/path/to/project", ai_helper)

# Analyze specific app
analysis, ai_prompt = app_analyzer.analyze_app(app_name, endpoints)

print(f"Models: {len(analysis['models'])}")
print(f"Serializers: {len(analysis['serializers'])}")
print(f"AI Prompt: {ai_prompt}")
```

## Example Output

```
============================================================
DjangoProbe - Intelligent endpoint testing for Django projects
============================================================

→ Analyzing input: /home/user/myproject
  Detected type: LOCAL

→ Validating source...
✓ Django project confirmed: /home/user/myproject

→ Resolving project...
✓ Project ready at: /home/user/.djangoprobe/cache/myproject

→ Scanning endpoints...
  Root URLs: myproject/urls.py
✓ Found 12 endpoint(s)

→ Generating and testing app by app...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Processing App: user (5 endpoints)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [dim]Read:[/dim] user/models.py [dim](2450 chars)[/dim]
  [dim]Read:[/dim] user/serializers.py [dim](1800 chars)[/dim]
  [dim]Read:[/dim] user/views.py [dim](3200 chars)[/dim]
  [dim]Read:[/dim] user/urls.py [dim](450 chars)[/dim]
  [dim]→ Generating AI prompt for user...[/dim]
  [green]✓ AI prompt generated (3200 chars)[/green]
  [dim]→ Generating test cases using AI prompt...[/dim]
  [green]✓ Generated 4500 chars of test code[/green]
  [green]✓ Written:[/green] tests/generated/test_user.py

  [dim]Running tests for:[/dim] tests.generated.test_user
  [dim]Ran 12 tests in 2.345s[/dim]
  [green]OK[/green]
  ✅ user: All tests passed!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Processing App: product (7 endpoints)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [dim]Read:[/dim] product/models.py [dim](3100 chars)[/dim]
  [dim]Read:[/dim] product/serializers.py [dim](2100 chars)[/dim]
  [dim]Read:[/dim] product/views.py [dim](2800 chars)[/dim]
  [dim]Read:[/dim] product/urls.py [dim](380 chars)[/dim]
  [dim]→ Generating AI prompt for product...[/dim]
  [green]✓ AI prompt generated (2800 chars)[/green]
  [dim]→ Generating test cases using AI prompt...[/dim]
  [green]✓ Generated 5200 chars of test code[/green]
  [green]✓ Written:[/green] tests/generated/test_product.py

  [dim]Running tests for:[/dim] tests.generated.test_product
  [dim]Ran 18 tests in 3.123s[/dim]
  [green]OK[/green]
  ✅ product: All tests passed!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                      Test Results Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ Total Tests: 30
  ✅ Passed: 30
  ❌ Failed: 0
  ⚠️  Errors: 0

  📊 Success Rate: 100.0%

  📄 Report saved to: /home/user/myproject/djangoprobe_report.json
```

## Requirements

- Python 3.8+
- Django 3.0+
- Django REST Framework 3.0+
- Groq API key (free tier available)

## Configuration Options

### Environment Variables

Required:
- `GROQ_API_KEY_1`: Your primary Groq API key

Optional:
- `GROQ_API_KEY_2`: Backup API key for rate limiting
- `GROQ_API_KEY_3`: Third backup API key

### CLI Options

```bash
djangoprobe SOURCE --enhanced

Options:
  --enhanced, -e    Enable AI-powered deep app analysis
  --help, -h         Show help message and exit
```

## Troubleshooting

### Common Issues

**Issue**: "No Groq API keys found"
- **Solution**: Add API keys to `.env` file as shown in Configuration section

**Issue**: "Rate limit exceeded"
- **Solution**: Add multiple API keys (`GROQ_API_KEY_2`, `GROQ_API_KEY_3`) for automatic rotation

**Issue**: Tests fail to run
- **Solution**: Ensure project has valid `manage.py` and all dependencies are installed

**Issue**: Authentication fails in tests
- **Solution**: Verify login URL is correctly detected and User model fields match

**Issue**: Enhanced mode is slow
- **Solution**: This is expected - enhanced mode performs deep analysis. Use standard mode for faster execution.

## Performance

### Standard Mode
- Analysis: ~5-10 seconds total
- Test Generation: ~10-20 seconds per app
- Execution: ~2-5 seconds per app

### Enhanced Mode
- Analysis: ~5-10 seconds per app
- Prompt Generation: ~10-20 seconds per app
- Test Generation: ~20-40 seconds per app
- Execution: ~2-5 seconds per app

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see LICENSE file for details

## Acknowledgments

- **Groq API**: For providing fast, free AI API access
- **Django REST Framework**: For the excellent API framework
- **Rich**: For beautiful terminal output
- **Typer**: For the elegant CLI framework

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/yourusername/djangoprobe/issues
- Documentation: See [ENHANCED_MODE.md](ENHANCED_MODE.md) for enhanced mode details

## Roadmap

- [ ] Support for GraphQL endpoints
- [ ] Performance testing generation
- [ ] Integration testing across related apps
- [ ] CI/CD integration
- [ ] Web dashboard for test results
- [ ] Custom test templates
- [ ] Parallel test execution
