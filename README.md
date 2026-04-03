# DjangoProbe

AI-powered Django API test runner that automatically discovers endpoints, generates intelligent test cases, and executes them with detailed reporting.

## Features

- **Automatic Endpoint Discovery**: Scans Django projects to find all API endpoints
- **AI-Powered Deep App Analysis**: Uses AI APIs to analyze models, serializers, and views
- **Multi-Provider Support**: Groq, Ollama (local), and Together AI with automatic fallback
- **Intelligent Test Generation**: Generates comprehensive test cases based on code analysis
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

Create a `.env` file in your project root. DjangoProbe supports multiple AI providers:

**Option 1: Ollama (Completely Free, Local)**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama and download a model
ollama serve &
ollama pull llama3.2

# No .env configuration needed - Ollama is auto-detected
```

**Option 2: Groq (Fast Remote API)**
```env
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.1-8b-instant  # Recommended for better rate limits
```

**Option 3: Together AI (Good Free Tier)**
```env
TOGETHER_API_KEY=your_key_here
TOGETHER_MODEL=meta-llama/Llama-3.1-8b-chat-Instruct-Turbo
```

**Multiple Providers (Best Reliability)**
```env
GROQ_API_KEY=gsk_your_key_here
TOGETHER_API_KEY=your_key_here
# Ollama will be auto-detected if running
```

For detailed setup instructions, see [MULTI_PROVIDER_SETUP.md](docs/MULTI_PROVIDER_SETUP.md).

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

### AI-Powered Analysis

DjangoProbe automatically performs deep app analysis:

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

**AI Analysis Features:**
- Deep analysis of models, serializers, and views
- AI-generated custom prompts for each app
- Better understanding of relationships and constraints
- More comprehensive test coverage
- App-specific test generation

For detailed information about the analysis process, see [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md).

## How It Works

DjangoProbe follows a modular pipeline with AI-powered deep app analysis:

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

### 5. Deep App Analysis & Test Generation
- Deeply analyzes each Django app using `AppAnalyzer`
- Parses models.py, serializers.py, views.py, urls.py
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
│   ├── app_analyzer.py             # Deep app analysis
│   ├── enhanced_test_generator.py  # AI-powered test generation
│   ├── ai_helper.py               # AI API communication (multi-provider)
│   ├── providers/                 # Multi-provider system
│   │   ├── __init__.py
│   │   ├── base.py               # Provider interface
│   │   ├── groq_provider.py      # Groq implementation
│   │   ├── ollama_provider.py    # Ollama implementation
│   │   ├── together_provider.py  # Together AI implementation
│   │   └── manager.py            # Provider manager with fallback
│   ├── app_test_runner.py         # Test execution
│   ├── report.py                  # Report generation
│   └── models.py                 # Data models
├── docs/
│   └── MULTI_PROVIDER_SETUP.md   # Multi-provider setup guide
├── examples/
│   └── enhanced_mode_demo.py      # Analysis demo
├── IMPLEMENTATION_SUMMARY.md      # Implementation details
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

### Complete Workflow

```python
from ai_tester import (
    EndpointScanner,
    ProjectAnalyzer,
    EnhancedTestGenerator,
    AppTestRunner
)

# Scan endpoints
scanner = EndpointScanner("/path/to/project")
endpoints = scanner.scan()

# Analyze project
analyzer = ProjectAnalyzer("/path/to/project")
analysis = analyzer.analyze()

# Generate tests with AI-powered analysis
generator = EnhancedTestGenerator(
    "/path/to/project",
    endpoints,
    analysis
)
test_files = generator.generate()

# Run tests
runner = AppTestRunner("/path/to/project")
for test_file in test_files:
    results = runner.run_custom_test_label(test_file)
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
- AI Provider (one or more):
  - **Ollama** (free, local) - Install from [ollama.ai](https://ollama.ai)
  - **Groq API key** (free tier) - Get from [console.groq.com](https://console.groq.com)
  - **Together AI key** (free tier) - Get from [api.together.xyz](https://api.together.xyz)

## Configuration Options

### Environment Variables

**AI Provider Selection:**
- `AI_PREFERRED_PROVIDER`: auto (default), groq, ollama, together

**Provider Configuration:**
- `GROQ_API_KEY`: Your Groq API key
- `GROQ_MODEL`: Groq model (default: llama-3.1-8b-instant)
- `TOGETHER_API_KEY`: Your Together AI key
- `TOGETHER_MODEL`: Together model (default: meta-llama/Llama-3.1-8b-chat-Instruct-Turbo)
- `OLLAMA_MODEL`: Ollama model (default: llama3.2)

**Retry Configuration:**
- `AI_MAX_RETRIES`: Maximum retry attempts (default: 3)
- `AI_RETRY_DELAY`: Delay between retries in seconds (default: 60)

### CLI Options

```bash
djangoprobe SOURCE

Options:
  --help, -h         Show help message and exit
```

## Troubleshooting

### Common Issues

**Issue**: "No AI providers available"
- **Solution**: Configure at least one provider (Ollama, Groq, or Together AI)

**Issue**: "Rate limit exceeded"
- **Solution**: Configure multiple providers for automatic fallback, or use Ollama for unlimited local usage

**Issue**: "Ollama not found"
- **Solution**: Install Ollama: `curl -fsSL https://ollama.ai/install.sh | sh`

**Issue**: Tests fail to run
- **Solution**: Ensure project has valid `manage.py` and all dependencies are installed

**Issue**: Authentication fails in tests
- **Solution**: Verify login URL is correctly detected and User model fields match

**Issue**: Analysis takes a long time
- **Solution**: This is expected - DjangoProbe performs deep code analysis for comprehensive test coverage. The time varies based on app complexity and AI provider speed.

**Issue**: AI provider errors (503, 429)
- **Solution**: The system will automatically rotate to the next available provider. Configure multiple providers for better reliability.

## Performance

### Analysis & Generation (per app)
- Deep App Analysis: ~5-10 seconds
- AI Prompt Generation: ~10-20 seconds
- Test Case Generation: ~20-40 seconds
- Execution: ~2-5 seconds

### Total Time per App
- Simple apps: ~35-70 seconds
- Complex apps: ~60-120 seconds

**Note**: Performance varies based on:
- App complexity (number of models, serializers, views)
- Codebase size
- Network latency for AI API calls
- Groq API rate limits

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see LICENSE file for details

## Acknowledgments

- **Groq API**: For providing fast, free AI API access
- **Ollama**: For completely free local AI model inference
- **Together AI**: For providing excellent free tier AI services
- **Django REST Framework**: For the excellent API framework
- **Rich**: For beautiful terminal output
- **Typer**: For the elegant CLI framework

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/yourusername/djangoprobe/issues
- Documentation: See [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for implementation details

## Roadmap

- [ ] Support for GraphQL endpoints
- [ ] Performance testing generation
- [ ] Integration testing across related apps
- [ ] CI/CD integration
- [ ] Web dashboard for test results
- [ ] Custom test templates
- [ ] Parallel test execution
