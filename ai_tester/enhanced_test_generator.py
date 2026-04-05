import re
import time
from pathlib import Path
from prompt_toolkit import token
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
        # Build app module map for correct imports
        self.app_module_map = self._build_app_module_map()

    def _build_app_module_map(self) -> dict[str, str]:
        """Build mapping of app names to their full module paths."""
        return {
            app.split('.')[-1]: app
            for app in self.ai_helper.installed_apps
            if app and '.' in app  # Only include apps with module paths
        }

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
            time.sleep(2)  # Brief _setup_output_dirpause between apps to avoid rate limits

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

        # Step 2.5: Validate generated code
        if not self._validate_generated_code(content, app_name):
            console.print(
                f"  [red]✗ Generated code validation failed for {app_name}[/red]"
            )
            return None

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
        # Build the system prompt with stronger constraints
        system_prompt = """You are an expert Django and DRF test engineer. You write clean, realistic, well-documented Django TestCase code.

        CRITICAL RULES - FOLLOW EXACTLY:
        1. Return ONLY valid Python code — NO markdown fences, NO explanation, NO preamble
        2. Code must be directly executable as a .py file
        3. Complete all methods with proper indentation and closing parentheses
        4. NEVER use relative imports (from .models import ...) — use absolute imports only
        5. NEVER use force_authenticate() — it doesn't exist on Django Client
        6. NEVER use client.login() if the project uses JWT authentication
        7. Import User model from the correct path, not django.contrib.auth.models

        Your task:
        1. Read the detailed analysis prompt provided
        2. Generate complete, comprehensive test cases for all endpoints
        3. Follow all instructions in the analysis prompt exactly
        4. Include proper setup, authentication, and assertions
        5. Test both success and failure cases
        6. Include edge cases and validation testing

        AUTHENTICATION SETUP - CRITICAL:
        - If the project uses JWT (most DRF projects do):
          - DO NOT use client.login() - it won't work with JWT
          - Create a helper method that authenticates and stores the token
          - Use Authorization header: self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
          - Example helper method structure:
            ```python
            def authenticate_jwt(self, email, password):
                payload = {'email': email, 'password': password}
                response = self.client.post('/api/user/login/', json.dumps(payload), content_type='application/json')
                if response.status_code == 200:
                    token = response.json()['access']
                    self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
            ```
        - If the project uses Django session auth (less common):
          - Use client.login() method
          - Example: self.client.login(email='test@example.com', password='password123')

        UUID FIELD HANDLING - CRITICAL:
        - When sending UUID fields in JSON payloads, ALWAYS convert to strings using str()
        - Example: 'role': str(role_obj.id) instead of 'role': role_obj.id
        - Example: 'pages': [str(page.id) for page in pages_list] instead of 'pages': [page.id for page in pages_list]
        - This is required because UUID objects cannot be directly JSON serialized
        - Include str() conversion in setUp() method and test methods

        IMPORT RULES:
        - Use absolute imports: from apps.app_name.models import ModelName
        - NEVER use relative imports: from .models import ModelName
        - Import User from the actual project location, not django.contrib.auth.models
        - Use: from django.test import TestCase, Client
        - Use: import json

        Return ONLY the Python code, nothing else."""

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

        ## CRITICAL AUTHENTICATION INFORMATION:
        """
            # Add specific authentication guidance based on auth type
            if self.analysis.auth_type == "JWT":
                # Check if we have detected the actual auth response structure
                token_path = 'access'  # default
                login_url = '/api/user/login/'  # default

                if structured_analysis and 'auth_response_structure' in structured_analysis:
                    auth_struct = structured_analysis['auth_response_structure']
                    if auth_struct and auth_struct.get('detected'):
                        token_path = auth_struct.get('token_path', 'access')
                        login_url = auth_struct.get('login_url', '/api/user/login/')
                        user_prompt += f"""
        - THIS PROJECT USES JWT AUTHENTICATION
        - DO NOT use client.login() - it will NOT work
        - You MUST create an authentication helper method
        - CRITICAL: The actual login response structure has been ANALYZED
        - Login URL: {login_url}
        - Access Token Path: response.json()['{token_path}']
        - Helper method should:
          1. Make a POST request to the login endpoint with credentials
          2. Extract the token from the response using the DETECTED path
          3. Set the Authorization header: self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer token'
        - Example authentication helper (uses DETECTED token path):
          ```python
          def authenticate_jwt(self, email, password):
              payload = {{'email': email, 'password': password}}
              response = self.client.post('{login_url}', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  token = response.json()['{token_path}']  # Use detected path
                  self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'
                  return response.json()
              return None
          ```
        - Call this helper in setUp() or test methods before authenticated requests
        - IMPORTANT: Use the exact token path '{token_path}', do NOT assume 'access'
"""
                    else:
                        user_prompt += f"""
        - THIS PROJECT USES JWT AUTHENTICATION
        - DO NOT use client.login() - it will NOT work
        - You MUST create an authentication helper method
        - Helper method should:
          1. Make a POST request to the login endpoint with credentials
          2. Extract the 'access' token from the response
          3. Set the Authorization header: self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        - Example authentication helper:
          ```python
          def authenticate_jwt(self, email, password):
              payload = {{'email': email, 'password': password}}
              response = self.client.post('/api/user/login/', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  token = response.json()['access']
                  self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'
          ```
        - Call this helper in setUp() or test methods before authenticated requests
"""
                else:
                    user_prompt += """
        - THIS PROJECT USES JWT AUTHENTICATION
        - DO NOT use client.login() - it will NOT work
        - You MUST create an authentication helper method
        - Helper method should:
          1. Make a POST request to the login endpoint with credentials
          2. Extract the 'access' token from the response
          3. Set the Authorization header: self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        - Example authentication helper:
          ```python
          def authenticate_jwt(self, email, password):
              payload = {'email': email, 'password': password}
              response = self.client.post('/api/user/login/', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  token = response.json()['access']
                  self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
          ```
        - Call this helper in setUp() or test methods before authenticated requests
"""
            else:
                user_prompt += """
        - This project uses Django session authentication
        - Use client.login() for authentication
        - Example: self.client.login(email='test@example.com', password='password123')
"""

            user_prompt += f"""
        ## CRITICAL USER MODEL INFORMATION:
        - DO NOT import from django.contrib.auth.models
        - The project uses a CUSTOM User model
        - User model is located at: {self.analysis.auth_module or 'apps.user.models' if self.analysis else 'apps.user.models'}
        - User model uses email as the identifier field (not username)
        - Create users using: User.objects.create_user(email='test@example.com', password='password123', full_name='Test User')
        - When importing, use: from {self.analysis.auth_module or 'apps.user.models'} import User

        ## CRITICAL UUID FIELD INFORMATION:
        - The project likely uses UUID primary keys for models
        - When sending UUID values in JSON payloads, ALWAYS convert to strings using str()
        - Example: 'role': str(role_obj.id) instead of 'role': role_obj.id
        - Example: 'pages': [str(page.id) for page in pages_list] instead of 'pages': [page.id for page in pages_list]
        - This is REQUIRED because UUID objects cannot be directly JSON serialized
        - Apply this conversion in setUp() method and test methods
"""

        # Add import path guidance for each app
        if self.app_module_map:
            user_prompt += "\n## CORRECT IMPORT PATHS FOR EACH APP:\n"
            for app_name, app_module in sorted(self.app_module_map.items()):
                user_prompt += f"- For '{app_name}' app: from {app_module}.models import ModelName\n"
            user_prompt += "- IMPORTANT: Use these exact import paths, not relative imports like 'from .models import'\n"

        # Add endpoint list
        user_prompt += "\n## Endpoints to Test:\n"
        for ep in app_endpoints:
            auth_status = "[REQUIRES AUTH]" if ep.requires_auth else "[PUBLIC]"
            user_prompt += f"- {', '.join(ep.http_methods)} {ep.url_pattern} {auth_status}\n"

        # Add import guidance with stronger warnings
        user_prompt += """
        ## CRITICAL IMPORT GUIDELINES:
        - Use: `from django.test import TestCase, Client`
        - Use: `import json`
        - Import models using ABSOLUTE paths: `from apps.{app_name}.models import ModelName`
        - DO NOT use relative imports like `from .models import ...`
        - DO NOT import from django.contrib.auth.models — use the custom User model path
        - DO NOT import serializers or services in tests

        ## CRITICAL AUTHENTICATION GUIDELINES:
        """

        # Add specific authentication guidance based on auth type
        if self.analysis and self.analysis.auth_type == "JWT":
            # Check if we have detected the actual auth response structure
            token_path = 'access'  # default
            login_url = '/api/user/login/'  # default

            if structured_analysis and 'auth_response_structure' in structured_analysis:
                auth_struct = structured_analysis['auth_response_structure']
                if auth_struct and auth_struct.get('detected'):
                    token_path = auth_struct.get('token_path', 'access')
                    login_url = auth_struct.get('login_url', '/api/user/login/')
                    user_prompt += f"""
        - THIS PROJECT USES JWT AUTHENTICATION
        - DO NOT use client.login() - it will NOT work
        - You MUST create an authentication helper method
        - CRITICAL: The actual login response structure has been ANALYZED
        - Login URL: {login_url}
        - Access Token Path: response.json()['{token_path}']
        - Example authentication helper (uses DETECTED token path):
          ```python
          def authenticate_jwt(self, email, password):
              payload = {{'email': email, 'password': password}}
              response = self.client.post('{login_url}', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  token = response.json()['{token_path}']  # CRITICAL: Use detected path
                  self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'
                  return response.json()
              return None
          ```
        - Call this helper in setUp() or before authenticated requests
        - IMPORTANT: Use the exact token path '{token_path}', do NOT assume 'access'
        - DO NOT use force_authenticate() — it doesn't exist on Django's Client
        - DO NOT use APIClient — use Django's test Client
"""
                else:
                    user_prompt += """
        - THIS PROJECT USES JWT AUTHENTICATION
        - DO NOT use client.login() - it will NOT work
        - You MUST create an authentication helper method
        - Helper method should make POST to login endpoint and set Authorization header
        - Example authentication helper:
          ```python
          def authenticate_jwt(self, email, password):
              payload = {'email': email, 'password': password}
              response = self.client.post('/api/user/login/', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  token = response.json()['access']
                  self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
          ```
        - Call this helper in setUp() or before authenticated requests
        - DO NOT use force_authenticate() — it doesn't exist on Django's Client
        - DO NOT use APIClient — use Django's test Client
"""
            else:
                user_prompt += """
        - THIS PROJECT USES JWT AUTHENTICATION
        - DO NOT use client.login() - it will NOT work
        - You MUST create an authentication helper method
        - Helper method should make POST to login endpoint and set Authorization header
        - Example authentication helper:
          ```python
          def authenticate_jwt(self, email, password):
              payload = {'email': email, 'password': password}
              response = self.client.post('/api/user/login/', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  token = response.json()['access']
                  self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
          ```
        - Call this helper in setUp() or before authenticated requests
        - DO NOT use force_authenticate() — it doesn't exist on Django's Client
        - DO NOT use APIClient — use Django's test Client
"""
        else:
            user_prompt += """
        - This project uses Django session authentication
        - Use client.login() for authentication
        - Example: self.client.login(email='test@example.com', password='password123')
        - DO NOT use force_authenticate() — it doesn't exist on Django's Client
        - DO NOT use APIClient — use Django's test Client
"""

        user_prompt += """
        ## CRITICAL UUID FIELD GUIDELINES:
        - When sending UUID field values in JSON payloads, ALWAYS convert to strings
        - Required for: foreign keys with UUID primary keys, many-to-many relationships
        - Examples:
          - `'role': str(role_obj.id)` instead of `'role': role_obj.id`
          - `'pages': [str(page.id) for page in pages_list]` instead of `'pages': [page.id for page in pages_list]`
          - `'user_id': str(user.id)` instead of `'user_id': user.id`
        - This is REQUIRED because UUID objects cannot be directly JSON serialized
        - Apply this conversion in setUp() method and all test methods

        ## Test Structure Guidelines:
        1. Create a test class that inherits from TestCase
        2. Implement setUp() method with authentication setup and test data creation
        3. Create separate test methods for each endpoint and HTTP method
        4. Include meaningful test method names (e.g., test_create_user_success, test_get_list_unauthorized)
        5. Use assertEqual, assertIn, assertTrue with descriptive messages
        6. Include both success and failure test cases
        7. Ensure all methods are complete with proper closing parentheses and indentation
        8. Convert all UUID values to strings before JSON serialization

        ## Response Codes:
        - 200: GET success
        - 201: POST success (created)
        - 204: DELETE success
        - 400: Bad request (validation error)
        - 401: Unauthorized
        - 403: Forbidden
        - 404: Not found
        - 405: Method not allowed

        Generate the complete test file now — ONLY Python code, no markdown, no explanation."""

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

    def _clear_existing_tests(self) -> None:
        """Clear all existing generated test files to force regeneration."""
        if self.output_dir.exists():
            for test_file in self.output_dir.glob("test_*.py"):
                try:
                    test_file.unlink()
                    console.print(f"  [yellow]🗑️ Deleted:[/yellow] {test_file.name}")
                except Exception as e:
                    console.print(f"  [yellow]⚠ Could not delete {test_file.name}: {e}[/yellow]")

    # HELPERS
    def _group_by_app(self) -> dict[str, list[EndpointInfo]]:
        """Group endpoints by app name."""
        groups: dict[str, list[EndpointInfo]] = {}
        for ep in self.endpoints:
            groups.setdefault(ep.app_name, []).append(ep)
        return groups

    def _validate_generated_code(self, content: str, app_name: str) -> bool:
        """
        Validate that the generated code is complete and syntactically correct.

        Returns:
            True if code is valid, False otherwise
        """
        console.print(f"    [dim]→ Validating generated code...[/dim]")

        # Check for basic Python syntax
        try:
            compile(content, f'<test_{app_name}>', 'exec')
        except SyntaxError as e:
            console.print(f"    [red]✗ Syntax error in generated code: {e}[/red]")
            return False

        # Check for required imports
        required_imports = ['from django.test import', 'import json']
        for required in required_imports:
            if required not in content:
                console.print(f"    [yellow]⚠ Missing required import: {required}[/yellow]")

        # Check for TestCase class
        if 'class' not in content or 'TestCase' not in content:
            console.print(f"    [yellow]⚠ No TestCase class found[/yellow]")
            return False

        # Check for test methods
        if 'def test_' not in content:
            console.print(f"    [yellow]⚠ No test methods found[/yellow]")
            return False

        # Check for strict assertions that might fail due to User model behavior differences
        # Some User models set is_staff/is_superuser automatically based on role
        if 'self.assertFalse(user.is_staff)' in content:
            console.print(f"    [yellow]⚠ Test assumes user.is_staff=False - User model may set this automatically[/yellow]")
        if 'self.assertFalse(user.is_superuser)' in content:
            console.print(f"    [yellow]⚠ Test assumes user.is_superuser=False - User model may set this automatically[/yellow]")

        # Check for relative imports (bad)
        if 'from .models import' in content or 'from .serializers import' in content:
            console.print(f"    [red]✗ Found relative imports - use absolute imports instead[/red]")
            return False

        # Check for wrong User import
        if 'from django.contrib.auth.models import User' in content:
            console.print(f"    [red]✗ Found django.contrib.auth.models.User - use custom User model[/red]")
            return False

        # REMOVED: Check for incorrect self.str() calls
        # The cleaning function handles this automatically with regex substitutions
        # This validation was causing false positives and skipping valid code
        # The cleaning regex patterns already handle: self.str(, self.str (, self.  str(
        # No need to validate here since it's handled during cleaning

        # Check for force_authenticate (bad)
        if 'force_authenticate' in content:
            console.print(f"    [red]✗ Found force_authenticate - use proper authentication method[/red]")
            return False

        # Check for JWT authentication if the project uses JWT
        if self.analysis and self.analysis.auth_type == "JWT":
            if 'client.login(' in content:
                console.print(f"    [yellow]⚠ Found client.login() in JWT project - should use JWT authentication[/yellow]")
            # Check for JWT token handling
            if 'HTTP_AUTHORIZATION' not in content and 'Bearer' not in content:
                console.print(f"    [yellow]⚠ JWT project missing Authorization header handling[/yellow]")
        else:
            # Check for session authentication if not JWT
            if 'HTTP_AUTHORIZATION' not in content and 'Bearer' not in content:
                if 'authenticate' not in content and 'client.login' not in content:
                    console.print(f"    [yellow]⚠ No authentication method found in tests[/yellow]")

        # Check for UUID string conversion
        if 'UUID' in content or 'uuid' in content:
            # Check if there's any str() conversion for UUID-like operations
            has_str_conversion = 'str(' in content and ('id' in content or '.id' in content)
            if has_str_conversion:
                console.print(f"    [green]✓ Found str() conversion - good for UUID handling[/green]")

        # Check for proper structure
        if not all([
            'setUp' in content,
            'def test_' in content,
            'self.client' in content,
        ]):
            console.print(f"    [yellow]⚠ Code may be missing essential test structure[/yellow]")

        console.print(f"    [green]✓ Code validation passed[/green]")
        return True

    def _clean_code(self, content: str) -> str:
        """
        Remove accidental markdown fences and clean up generated code.

        This method:
        1. Removes markdown code fences (```python, ```, etc.)
        2. Removes explanatory text before/after code
        3. Fixes common AI-generated issues
        4. Validates and ensures code completeness
        """
        # Strip whitespace
        content = content.strip()

        # Remove markdown code fences at the start
        if content.startswith("```python"):
            content = content[len("```python"):].strip()
        if content.startswith("```"):
            content = content[3:].strip()

        # Remove markdown code fences at the end
        if content.endswith("```"):
            content = content[:-3].strip()

        # Remove common AI-generated explanatory text
        explanatory_patterns = [
            r'^(Here is|Here\'s|Below is|The following is|Here are|Below are)\s+(the|a|some|complete)?\s*',
            r'^(I have|I\'ve|I will|I would|I can)\s+',
            r'^(Let me|Allow me to|I will now)\s+',
            r'^(This code|The code|These tests|The tests)\s+',
            r'^(Note:|Note that|Please note:)\s+',
            r'^(You can|You should|You may)\s+',
            r'^(The above|The following|This)\s+(code|test|tests|implementation|file)\s+',
            r'^(Complete|Comprehensive|Full|Detailed|Working)\s+',
        ]

        for pattern in explanatory_patterns:
            if re.match(pattern, content, re.IGNORECASE):
                lines = content.split('\n')
                # Remove lines that match the pattern
                lines = [line for line in lines if not re.match(pattern, line.strip(), re.IGNORECASE)]
                content = '\n'.join(lines).strip()

        # Remove lines that are purely explanatory (not code)
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip lines that look like AI explanations
            if stripped.startswith('#') and any(word in stripped.lower() for word in
                ['note', 'explanation', 'here is', 'this code', 'the test', 'complete', 'comprehensive', 'working']):
                continue
            # Skip lines that look like markdown headers
            if stripped.startswith('#') and stripped.count('#') >= 2:
                continue
            # Skip empty lines at the start
            if not cleaned_lines and not stripped:
                continue
            cleaned_lines.append(line)

        content = '\n'.join(cleaned_lines).strip()

        # Fix common relative imports - replace with absolute imports
        # This is a basic fix - more complex cases might need manual review
        content = re.sub(r'from \.models import', f'from apps.{self.repo_path.name} import', content)
        content = re.sub(r'from \.serializers import', f'from apps.{self.repo_path.name} import', content)
        content = re.sub(r'from \.views import', f'from apps.{self.repo_path.name} import', content)

        # Fix incorrect self.str() calls - replace with built-in str()
        # Pattern: self.str(something) -> str(something)
        # Multiple patterns to catch variations
        content = re.sub(r'self\.str\(', r'str(', content)  # self.str(
        content = re.sub(r'self\.str \(', r'str(', content)  # self.str (
        content = re.sub(r'self\.  str\(', r'str(', content)  # self.  str(

        # Fix force_authenticate usage - replace with proper authentication
        # For JWT projects, replace with JWT authentication pattern
        if self.analysis and self.analysis.auth_type == "JWT":
            # Try to replace force_authenticate with JWT authentication
            content = re.sub(
                r'self\.client\.force_authenticate\(user=self\.test_user\)',
                'self.authenticate_jwt(self.test_user.email, "password123")',
                content
            )
            content = re.sub(
                r'self\.client\.force_authenticate\([^)]+\)',
                '# Use self.authenticate_jwt(email, password) for JWT authentication',
                content
            )
        else:
            # For session auth, replace with login()
            content = re.sub(
                r'self\.client\.force_authenticate\(user=self\.test_user\)',
                'self.client.login(email=self.test_user.email, password="password123")',
                content
            )
            content = re.sub(
                r'self\.client\.force_authenticate\([^)]+\)',
                '# Note: Use client.login() for authentication',
                content
            )

        # Fix UUID serialization - common patterns
        # Pattern 1: 'role': role_obj.id -> 'role': str(role_obj.id)
        content = re.sub(
            r"'role':\s*(\w+\.id)",
            r"'role': str(\1)",
            content
        )
        # Pattern 2: 'pages': [page.id for page in pages] -> 'pages': [str(page.id) for page in pages]
        content = re.sub(
            r"'pages':\s*\[([^.]+)\.id\s+for\s+([^.]+)\s+in\s+([^.]+)\]",
            r"'pages': [str(\1.id) for \2 in \3]",
            content
        )
        # Pattern 3: Generic UUID field references in dict comprehensions
        content = re.sub(
            r"(\w+\.id)(?=\s*[,}])",
            r"str(\1)",
            content
        )

        # Validate basic Python syntax
        try:
            compile(content, '<string>', 'exec')
        except SyntaxError as e:
            console.print(f"    [yellow]⚠ Syntax warning in generated code: {e}[/yellow]")
            # Try to fix common issues
            # Check for unmatched parentheses
            open_parens = content.count('(')
            close_parens = content.count(')')
            if open_parens > close_parens:
                content += ')' * (open_parens - close_parens)

            open_brackets = content.count('[')
            close_brackets = content.count(']')
            if open_brackets > close_brackets:
                content += ']' * (open_brackets - close_brackets)

            open_braces = content.count('{')
            close_braces = content.count('}')
            if open_braces > close_braces:
                content += '}' * (open_braces - close_braces)

        return content


def generate_with_enhanced_analyzer(
    repo_path: str,
    endpoints: list[EndpointInfo],
    analysis=None,
    force_regenerate: bool = False,
) -> list[str]:
    """
    Convenience function to generate tests with enhanced AI-powered analysis.

    Args:
        repo_path: Path to the Django project
        endpoints: List of discovered endpoints
        analysis: ProjectAnalysis object (optional)
        force_regenerate: If True, delete existing test files before regenerating

    Returns:
        List of generated test file paths
    """
    generator = EnhancedTestGenerator(
        repo_path=repo_path,
        endpoints=endpoints,
        analysis=analysis,
    )

    if force_regenerate:
        generator._clear_existing_tests()

    return generator.generate()
