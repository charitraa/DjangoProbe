# DjangoProbe Enhanced Mode

## Overview

DjangoProbe now supports an **Enhanced Mode** that uses AI-powered deep app analysis to generate more intelligent and comprehensive test cases.

## Standard Mode vs Enhanced Mode

### Standard Mode (Default)
- Uses manually crafted prompts for test generation
- Generates tests directly to each app's `tests.py` file
- Faster execution but less context-aware

### Enhanced Mode (`--enhanced` flag)
- Uses AI to deeply analyze each Django app
- Generates custom prompts based on app-specific code analysis
- Examines models, serializers, views, and relationships
- Creates more comprehensive test cases with better coverage
- Generates tests to `tests/generated/test_<app_name>.py`

## How Enhanced Mode Works

The enhanced mode follows a sophisticated 3-step process for each Django app:

### Step 1: Deep App Analysis
The `AppAnalyzer` module performs comprehensive analysis:
- **Models Analysis**: Extracts all models, their fields, field types, required/optional status
- **Serializers Analysis**: Examines serializers, identifies ModelSerializer relationships, required fields, read-only fields
- **Views Analysis**: Analyzes class-based and function-based views, extracts HTTP methods and permissions
- **Relationship Extraction**: Identifies ForeignKey and ManyToMany relationships between models
- **Endpoint Mapping**: Maps views to their URL patterns and HTTP methods

### Step 2: AI-Powered Prompt Generation
Using the structured analysis, the AI generates a custom prompt that includes:
- Complete model information with field types and constraints
- Serializer requirements (what data is needed for POST/PUT operations)
- View permissions and authentication requirements
- Relationship handling (create FK objects first, set M2M after)
- Specific test data guidelines and edge cases
- Detailed endpoint-specific instructions

### Step 3: Test Case Generation
Using the AI-generated prompt, comprehensive test cases are created that:
- Include proper setup with authentication
- Test all HTTP methods for each endpoint
- Handle relationships correctly
- Test both success and failure scenarios
- Include validation testing
- Cover edge cases and error conditions

## Usage

### Basic Usage
```bash
# Standard mode (default)
djangoprobe /path/to/django/project

# Enhanced mode with AI-powered analysis
djangoprobe /path/to/django/project --enhanced

# Short form
djangoprobe /path/to/django/project -e
```

### Remote Repository
```bash
# Enhanced mode for GitHub repository
djangoprobe https://github.com/user/repo --enhanced

# Enhanced mode for GitLab repository
djangoprobe https://gitlab.com/user/repo --enhanced

# Enhanced mode for SSH URL
djangoprobe git@github.com:user/repo.git --enhanced
```

## Enhanced Mode Output

### Console Output
The enhanced mode provides detailed progress information:
```
[bold cyan]============================================================[/bold cyan]
[bold cyan]Processing App:[/bold cyan] [green]user[/green] [dim](5 endpoints)[/dim]
[bold cyan]============================================================[/bold cyan]

    [dim]Read:[/dim] user/models.py [dim](2450 chars)[/dim]
    [dim]Read:[/dim] user/serializers.py [dim](1800 chars)[/dim]
    [dim]Read:[/dim] user/views.py [dim](3200 chars)[/dim]
    [dim]Read:[/dim] user/urls.py [dim](450 chars)[/dim]
    [dim]→ Generating AI prompt for user...[/dim]
    [green]✓ AI prompt generated (3200 chars)[/green]
    [dim]→ Generating test cases using AI prompt...[/dim]
    [dim]Calling AI model...[/dim]
    [green]✓ Generated 4500 chars of test code[/green]
  [green]✓ Written:[/green] tests/generated/test_user.py
```

### Generated Test Files
Enhanced mode generates tests to:
```
/path/to/project/tests/generated/
├── __init__.py
├── test_user.py
├── test_product.py
├── test_order.py
└── backup/
    ├── test_user_20260402_123045.py
    └── test_product_20260402_123047.py
```

## Analysis Details

### What Gets Analyzed

#### Models
- All model classes and their fields
- Field types (CharField, IntegerField, etc.)
- Required vs optional fields (based on `blank=False`, `null=False`)
- Default values and choices
- Primary keys and auto-generated fields

#### Serializers
- All serializer classes
- ModelSerializer relationships
- Required fields for POST/PUT operations
- Read-only fields (should not be included in test data)
- Validation rules and custom methods

#### Views
- Class-based views (APIView, ModelViewSet, etc.)
- Function-based views (@api_view decorators)
- HTTP methods supported (GET, POST, PUT, PATCH, DELETE)
- Permission classes and authentication requirements
- URL patterns and parameters

#### Relationships
- ForeignKey relationships and required status
- ManyToMany fields
- Related model names and creation order
- Cascading behaviors

### AI Prompt Components

The AI-generated prompt includes:
1. **Model Information**: Complete list of models with all fields
2. **Serializer Information**: All serializers with required/read-only fields
3. **View Information**: Views with methods and permissions
4. **Endpoint Information**: URLs, methods, and authentication requirements
5. **Test Data Guidelines**: What data to create and how
6. **Authentication Setup**: User creation and authentication details
7. **Relationship Handling**: How to handle FK and M2M relationships

## Benefits of Enhanced Mode

### Better Test Coverage
- Analyzes actual code structure
- Identifies all relationships and constraints
- Tests validation rules
- Covers edge cases

### More Accurate Tests
- Uses actual field names and types
- Respects serializer requirements
- Handles authentication correctly
- Includes proper relationship setup

### Reduced False Positives
- Only tests what's actually in the code
- Avoids testing non-existent fields
- Uses correct data types and formats

### Faster Development
- No manual prompt engineering
- App-specific test generation
- Comprehensive coverage out of the box

## Architecture

### New Components

1. **`app_analyzer.py`**: Deep app analysis module
   - Collects and parses source code
   - Extracts structured information
   - Identifies relationships and requirements

2. **`enhanced_test_generator.py`**: Enhanced test generation
   - Orchestrates the analysis and generation process
   - Coordinates AI calls for prompt generation and test creation
   - Manages file writing and backups

3. **Updated CLI**: Enhanced mode support
   - `--enhanced` flag to enable enhanced mode
   - Modified test running for generated tests
   - Progress reporting for each step

### Integration Points

- **Endpoint Scanner**: Used for endpoint discovery (unchanged)
- **Project Analyzer**: Used for global project analysis (unchanged)
- **AI Helper**: Used for AI API calls (enhanced with analyzer integration)
- **App Test Runner**: Modified to run tests from `tests/generated/` directory
- **Test Generator**: New enhanced version replaces standard generator in enhanced mode

## Examples

### Example Output: User App Analysis
```
### Models:

**User**
  - email: EmailField (required)
  - full_name: CharField (required)
  - role: ForeignKey (required)
  - groups: ManyToManyField (optional)

### Serializers:

**UserSerializer** (Model: User)
  - email: EmailField [REQUIRED]
  - full_name: CharField [REQUIRED]
  - role: ForeignKey [REQUIRED]
  - id: IntegerField [READ-ONLY]

### Views:

**UserViewSet** (class_based)
  Methods: GET, POST, PUT, PATCH, DELETE
  Permissions: IsAuthenticated

### Endpoints:
  - ['GET', 'POST'] /api/user/ [AUTH]
  - ['GET', 'PUT', 'PATCH', 'DELETE'] /api/user/{id}/ [AUTH]

### Foreign Key Relationships:
  - User.role → Role [required]

### Many-to-Many Relationships:
  - User.groups → Group
```

## Performance Considerations

- **Analysis Time**: ~5-10 seconds per app for code analysis
- **Prompt Generation**: ~10-20 seconds per app for AI prompt generation
- **Test Generation**: ~20-40 seconds per app for test code generation
- **Total Time**: Approximately 1-2 minutes per app (vs 10-20 seconds in standard mode)

The enhanced mode is slower but produces significantly better test quality.

## Future Enhancements

Planned improvements to enhanced mode:
- [ ] Cache analysis results for repeated runs
- [ ] Support for custom model managers
- [ ] Analysis of signals and their effects
- [ ] Business logic extraction from services layer
- [ ] Integration testing across related apps
- [ ] Performance testing generation

## Troubleshooting

### Common Issues

**Issue**: AI prompt generation fails
- **Solution**: Check Groq API keys are valid and have sufficient quota
- **Solution**: Ensure network connectivity to Groq API

**Issue**: Tests fail to run from generated directory
- **Solution**: Ensure `tests/generated/` directory is in Python path
- **Solution**: Check that `tests/__init__.py` exists

**Issue**: Missing relationships in analysis
- **Solution**: Verify models.py is parseable (no syntax errors)
- **Solution**: Check that ForeignKey imports are correct

**Issue**: Authentication fails in tests
- **Solution**: Verify login URL is correctly detected
- **Solution**: Check User model fields match analysis

## Contributing

To contribute to the enhanced mode:
1. Run tests with `--enhanced` flag
2. Analyze generated prompts for improvements
3. Submit issues with sample Django projects
4. Suggest improvements to the analysis logic

## License

Same as DjangoProbe project license.
