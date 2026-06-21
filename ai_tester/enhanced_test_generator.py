import re
import time
from pathlib import Path
from rich.console import Console
from ai_tester.models import EndpointInfo
from ai_tester.ai_helper import AIHelper
from ai_tester.app_analyzer import AppAnalyzer

console = Console()

# A password strong enough to pass Django's default AUTH_PASSWORD_VALIDATORS
# (min length, not all-numeric, not a common password, not similar to the
# username/email). Registration endpoints run these validators, so weak
# defaults like "password123" make create/register success tests return 400.
STRONG_TEST_PASSWORD = "Str0ng!Pass99"


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
        """Build mapping of app last-segment names to their full module paths.

        `ai_helper.installed_apps` is a list of dicts: {module, app_name, app_dir}.
        The previous implementation treated each entry as a string and silently
        produced an empty map — which broke both the prompt's import guidance and
        the hallucinated-import validator.
        """
        return {
            app["app_name"]: app["module"]
            for app in self.ai_helper.installed_apps
            if app.get("app_name") and app.get("module")
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

        # Step 2.5: Validate generated code with retry mechanism
        validated, content = self._validate_generated_code(content, app_name)
        if not validated:
            console.print(
                f"  [red]✗ Generated code validation failed for {app_name}[/red]"
            )
            # Retry once with a simpler prompt
            console.print(f"  [yellow]→ Retrying with simpler prompt...[/yellow]")
            content = self._retry_with_simpler_prompt(app_name, app_endpoints, ai_prompt, structured_analysis)
            if content:
                content = self._clean_code(content)
                validated, content = self._validate_generated_code(content, app_name)
                if not validated:
                    console.print(
                        f"  [red]✗ Retry also failed for {app_name}[/red]"
                    )
                    return None
            else:
                console.print(
                    f"  [red]✗ Retry generation failed for {app_name}[/red]"
                )
                return None

        # Step 3: Write to file
        written = self._write_test_file(app_name, content, file_path)
        return written

    def _jwt_auth_guidance(self, structured_analysis: dict) -> str:
        """Build JWT authentication guidance for the generation prompt.

        Defaults to header-based Bearer-token auth (``Authorization: Bearer
        <access>``) -- the standard flow for simple DRF CRUD APIs. Cookie-based
        JWT is only emitted when the analysis explicitly detected it, and the
        login URL / token path / response shape come from the detected auth
        structure so nothing is hardcoded.
        """
        token_path = "access"
        login_url = (
            self.analysis.login_url
            if self.analysis and self.analysis.login_url
            else "/api/user/login/"
        )
        response_format = "flat"
        auth_method = "header_jwt"
        data_key = "data"
        # Login credential field: "username" for stock User, "email" for custom users.
        cred = self.analysis.username_field if self.analysis else "email"

        if structured_analysis and "auth_response_structure" in structured_analysis:
            auth_struct = structured_analysis["auth_response_structure"] or {}
            if auth_struct.get("detected"):
                token_path = auth_struct.get("token_path", token_path)
                # Prefer ProjectAnalyzer's login_url (resolves the URL include
                # prefix); only fall back to the app-level one if it's absent.
                if not (self.analysis and self.analysis.login_url):
                    login_url = auth_struct.get("login_url", login_url)
                response_format = auth_struct.get("response_format", response_format)
                auth_method = auth_struct.get("auth_method", auth_method)
                data_key = auth_struct.get("data_key", data_key)

        # Build the token-extraction line, honouring the detected response shape.
        if response_format == "nested":
            extract = (
                f"token = data.get('{data_key}', {{}}).get('{token_path}') "
                f"or data.get('{token_path}')"
            )
        else:
            extract = f"token = data.get('{token_path}')"

        if auth_method == "cookie_jwt":
            cookie_names = (
                (structured_analysis or {}).get("auth_response_structure") or {}
            ).get("cookie_names", [])
            main_cookie = cookie_names[0] if cookie_names else "access_token"
            return f"""
        - THIS PROJECT USES COOKIE-BASED JWT AUTHENTICATION (detected)
        - DO NOT use client.login() and DO NOT use force_authenticate()
        - Authenticate by logging in and storing the JWT in the request cookies
        - Login URL: {login_url}  |  Token path: '{token_path}' (response format: {response_format})
        - Example authentication helper:
          ```python
          def authenticate_jwt(self, {cred}, password):
              payload = {{'{cred}': {cred}, 'password': password}}
              response = self.client.post('{login_url}', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  data = response.json()
                  {extract}
                  if token:
                      self.client.cookies['{main_cookie}'] = token
                  return data
              return None
          ```
        - Call this helper in setUp() before authenticated requests
        - DO NOT use APIClient -- use Django's test Client
"""

        # Default: header-based Bearer token auth (simple CRUD APIs).
        return f"""
        - THIS PROJECT USES JWT AUTHENTICATION WITH BEARER TOKENS
        - Authenticate via the Authorization header: f'Bearer <access token>'
        - DO NOT use client.login(), force_authenticate(), or cookies for auth
        - Login URL: {login_url}  |  Access token path: '{token_path}' (response format: {response_format})
        - Example authentication helper:
          ```python
          def authenticate_jwt(self, {cred}, password):
              payload = {{'{cred}': {cred}, 'password': password}}
              response = self.client.post('{login_url}', data=json.dumps(payload), content_type='application/json')
              if response.status_code == 200:
                  data = response.json()
                  {extract}
                  if token:
                      self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'
                  return data
              return None
          ```
        - Call this helper in setUp() before authenticated requests
        - DO NOT use APIClient -- use Django's test Client
"""

    def _user_model_guidance(self) -> str:
        """Build User-model guidance from the detected analysis.

        Adapts to the project's real User model: the login credential field
        (username vs email), the fields safe to pass to create_user(), and the
        correct import. Replaces the old hardcoded email/full_name assumptions
        that broke stock django.contrib.auth.User projects.
        """
        a = self.analysis
        module = a.auth_module if a and a.auth_module else None
        cred = a.username_field if a else "email"
        fields = list(a.safe_user_fields) if a and a.safe_user_fields else ["email", "full_name"]

        example_vals = {
            "username": "'testuser'",
            "email": "'test@example.com'",
            "full_name": "'Test User'",
            "name": "'Test User'",
            "first_name": "'Test'",
            "last_name": "'User'",
            "phone": "'1234567890'",
        }
        kwargs = [f"{f}={example_vals.get(f, chr(39) + 'value' + chr(39))}" for f in fields if f != "password"]
        kwargs.append(f"password='{STRONG_TEST_PASSWORD}'")
        create_call = "User.objects.create_user(" + ", ".join(kwargs) + ")"

        module_line = (
            f"        - The custom User model lives at: {module}\n"
            if module and module not in ("apps.user", "apps.user.models", "django.contrib.auth")
            else ""
        )

        return f"""        ## CRITICAL USER MODEL INFORMATION:
        - Import the User model with: from django.contrib.auth import get_user_model; User = get_user_model()
        - The login credential field is '{cred}' -- use it for both login and create_user()
        - Create test users like: {create_call}
{module_line}        - Only pass these fields to create_user(): {', '.join(fields)} (plus password)
        - Do NOT invent User fields that are not listed above

        ## CRITICAL PASSWORD RULES (registration endpoints validate passwords):
        - For any user that must successfully register/log in, use this exact password: '{STRONG_TEST_PASSWORD}'
        - Use the SAME password in setUp create_user(), in login, and in register-success tests
        - This password passes Django's validators (>=8 chars, not all-numeric, not a
          common password, not similar to the username/email)
        - NEVER use weak passwords like 'password123' for success tests -- the register
          endpoint runs validate_password and will return 400, failing the test
        - Only use a deliberately weak password (e.g. '123') in tests that EXPECT a 400"""

    def _is_pagination_enabled(self) -> bool:
        """Detect whether DRF list endpoints are paginated for this project.

        A list endpoint only returns a {'count', 'results': [...]} envelope when
        a default pagination class (or global PAGE_SIZE) is configured. Without
        it, DRF returns a plain JSON array — assuming 'results' then raises
        TypeError/KeyError in generated tests.
        """
        for settings_file in self.repo_path.rglob("settings.py"):
            if any(part in {"site-packages", ".venv", "env", ".probe_venv"}
                   for part in settings_file.parts):
                continue
            try:
                content = settings_file.read_text(errors="ignore")
            except OSError:
                continue
            if "DEFAULT_PAGINATION_CLASS" in content or "PAGE_SIZE" in content:
                return True
        return False

    def _ownership_scoping_guidance(self, app_name: str) -> str:
        """Prompt guidance for viewsets that scope their queryset to request.user.

        When ``get_queryset`` filters by the authenticated user (a very common
        ownership pattern), another user's object is simply absent from the
        queryset, so DRF returns 404 (not 403) on detail access, and list
        endpoints only ever return the current user's objects.
        """
        app = next((a for a in self.ai_helper.installed_apps
                    if a.get("app_name") == app_name), None)
        views_path = None
        if app and app.get("app_dir"):
            candidate = Path(app["app_dir"]) / "views.py"
            if candidate.exists():
                views_path = candidate
        if views_path is None:
            candidate = self.repo_path / app_name / "views.py"
            views_path = candidate if candidate.exists() else None
        if views_path is None:
            return ""
        try:
            views_src = views_path.read_text(errors="ignore")
        except OSError:
            return ""

        # Detect: get_queryset that filters on the request user.
        if not re.search(r"def get_queryset[\s\S]*?request\.user", views_src):
            return ""

        return """
        ## OBJECT OWNERSHIP SCOPING - CRITICAL:
        - A viewset here filters its queryset by the authenticated user (owner scoping).
        - Therefore another user's object is NOT in the queryset: detail/PUT/PATCH/DELETE
          on an object the current user does NOT own returns 404, NOT 403.
        - For "not owner"/"forbidden" style tests, assert status_code == 404 (not 403).
        - List endpoints only ever return the CURRENT user's objects — assert counts accordingly.
"""

    def _list_response_guidance(self) -> str:
        """Prompt guidance on the shape of list (GET collection) responses."""
        if self._is_pagination_enabled():
            return """
        ## LIST RESPONSE SHAPE - CRITICAL:
        - This project HAS DRF pagination enabled, so list (GET collection)
          endpoints return a paginated envelope: {'count': N, 'next': ..., 'previous': ..., 'results': [...]}
        - Access items via response.json()['results'], and assert with assertIn('results', response.json())
"""
        return """
        ## LIST RESPONSE SHAPE - CRITICAL:
        - This project has NO DRF pagination configured, so list (GET collection)
          endpoints return a PLAIN JSON ARRAY, e.g. [{'id': 1, ...}, ...]
        - response.json() is a list, NOT a dict. Do NOT access response.json()['results']
          and do NOT assert assertIn('results', response.json()) — both will fail.
        - To count items use len(response.json()); to inspect the first item use response.json()[0]
"""

    def _test_data_guidance(self, structured_analysis: dict) -> str:
        """Guidance on seeding test data and writing correct failure cases.

        Two recurring mistakes in generated tests:
        1. A list-success test asserts a non-empty result without creating any
           object first — but querysets are commonly owner-scoped, so the list
           starts empty and the assertion fails.
        2. A create/update "failure" test omits an OPTIONAL field expecting a
           400 — but only REQUIRED fields trigger validation errors.
        """
        # Pull client-providable required fields from the analyzed models: a
        # field a client must send is required, has no default, and isn't an
        # auto/timestamp or server-set relation (owner/FK, set by the view).
        required = []
        _auto_types = {"DateTimeField", "AutoField", "BigAutoField", "ForeignKey", "ManyToManyField"}
        if isinstance(structured_analysis, dict):
            for model in structured_analysis.get("models", []) or []:
                if not isinstance(model, dict) or model.get("name") == "Meta":
                    continue
                for field in model.get("fields", []) or []:
                    if not isinstance(field, dict):
                        continue
                    if (
                        field.get("required")
                        and not field.get("default")
                        and field.get("type") not in _auto_types
                        and field.get("name") not in ("id", "owner")
                    ):
                        name = str(field.get("name"))
                        if name and name not in required:
                            required.append(name)

        required_line = (
            f"        - REQUIRED fields for create (omit/empty ONE of these to force a 400): {', '.join(required)}\n"
            if required else
            "        - To force a 400, omit or empty a REQUIRED field (not an optional/blank one).\n"
        )

        return f"""
        ## TEST DATA & FAILURE CASES - CRITICAL:
        - For any LIST success test that asserts a non-empty result, FIRST create
          at least one object owned by the authenticated user (e.g. via the model's
          .objects.create(..., owner=self.user)) so the list is not empty.
        - Only assert a non-empty list AFTER creating objects in that test.
{required_line}        - Do NOT expect a 400 just for omitting an optional field — it will return 201/200.
"""

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
        7. Import User model using get_user_model() OR from apps.{app_name}.models import User NEVER use: from apps.{app_name} import User

        Your task:
        1. Read the detailed analysis prompt provided
        2. Generate complete, comprehensive test cases for all endpoints
        3. Follow all instructions in the analysis prompt exactly
        4. Include proper setup, authentication, and assertions
        5. Test both success and failure cases
        6. Include edge cases and validation testing

        AUTHENTICATION SETUP - CRITICAL:
        - Default to JWT with Bearer tokens (the standard for DRF CRUD APIs):
          - DO NOT use client.login() or force_authenticate() with JWT - they won't work
          - Create a helper that logs in, stores the access token, and sends it as a header
          - Set the header: self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
          - Example helper method structure:
            ```python
            def authenticate_jwt(self, email, password):
                payload = {'email': email, 'password': password}
                response = self.client.post('/api/user/login/', json.dumps(payload), content_type='application/json')
                if response.status_code == 200:
                    token = response.json().get('access', response.json().get('token'))
                    self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
                    return response.json()
            ```
        - Only use cookie-based JWT (self.client.cookies[...]) if the analysis prompt
          explicitly says the project uses cookie-based authentication.
        - Only use client.login() if the analysis says the project uses Django session auth.

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
                user_prompt += self._jwt_auth_guidance(structured_analysis)
            else:
                user_prompt += """
        - This project uses Django session authentication
        - Use client.login() for authentication
        - Example: self.client.login(email='test@example.com', password='Str0ng!Pass99')
"""

            user_model_info = self._user_model_guidance()
            user_prompt += f"""
{user_model_info}

        ## CRITICAL UUID FIELD INFORMATION:
        - The project likely uses UUID primary keys for models
        - When sending UUID values in JSON payloads, ALWAYS convert to strings using str()
        - Example: 'role': str(role_obj.id) instead of 'role': role_obj.id
        - Example: 'pages': [str(page.id) for page in pages_list] instead of 'pages': [page.id for page in pages_list]
        - This is REQUIRED because UUID objects cannot be directly JSON serialized
        - Apply this conversion in setUp() method and test methods

        ## CRITICAL IMAGE FILE CREATION (if app uses images):
        - When creating test image files using PIL/Pillow, use correct format names
        - For JPG files: image.save(file, 'JPEG') NOT 'jpg' or 'JPG'
        - For PNG files: image.save(file, 'PNG') NOT 'png'
        - Pillow requires uppercase format names, not lowercase
        - Example helper method:
          ```python
          def _create_image_file(self, name='test.jpg'):
              file = BytesIO()
              image = Image.new('RGB', (100, 100), 'red')
              image.save(file, 'JPEG')  # Use 'JPEG', 'PNG', etc. - uppercase
              file.seek(0)
              return SimpleUploadedFile(name, file.getvalue(), content_type='image/jpeg')
          ```
"""

            user_prompt += self._list_response_guidance()
            user_prompt += self._ownership_scoping_guidance(app_name)
            user_prompt += self._test_data_guidance(structured_analysis)

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
            user_prompt += self._jwt_auth_guidance(structured_analysis)
        else:
            user_prompt += """
        - This project uses Django session authentication
        - Use client.login() for authentication
        - Example: self.client.login(email='test@example.com', password='Str0ng!Pass99')
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

        ## CRITICAL URL PATTERNS:
        - Use the API prefix from settings (usually /api/)
        - Include app name in URL: /api/<app_name>/<endpoint>
        - Use actual URL paths directly (NOT reverse() with namespaced names)
        - Example CORRECT usage: self.client.get('/api/enquiry/list/')
        - Example WRONG usage: reverse('enquiry:list') - this won't work because namespace may not be registered
        - For endpoints with UUID parameters: /api/enquiry/get/<uuid>/ - use actual UUID values in tests
        - DO NOT make up URLs - use the exact URL paths listed in endpoints above

        ## CRITICAL IMPORT PATTERNS:
        - Use this format: from apps.<app_name>.models import ModelName
        - Example: from apps.apply.models import Application (NOT from apps.apply import Application)
        - Example: from apps.user.models import User (NOT from apps.user import User)
        - DO NOT use: from apps.<app_name> import <model> - this imports the app module, not the model
        - DO NOT use: from django.contrib.auth.models import User - use custom user model
        - For User model: from apps.user.models import User

        ## CRITICAL SETUP ORDER:
        - In setUp(), FIRST create all test data (self.user, self.user_data, etc.)
        - THEN call authenticate() method AFTER data is ready
        - WRONG ORDER: self.auth = self.get_auth_helper() before self.user_data is set
        - CORRECT ORDER: 1) self.user_data = {...}  2) self.user = User.objects.create(...)  3) self.authenticate()

        ## CRITICAL AUTHENTICATION FOR THIS PROJECT:
        - This project uses JWT with Bearer-token authentication
        - Log in, read the access token from the response, and send it as a header
        - The correct authentication helper pattern:
          ```python
          def authenticate(self):
              response = self.client.post('/api/user/login/',
                  data=json.dumps({'email': 'test@example.com', 'password': 'Str0ng!Pass99'}),
                  content_type='application/json')
              if response.status_code == 200:
                  data = response.json()
                  token = data.get('access') or data.get('data', {}).get('access')
                  if token:
                      self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
          ```
        - Call authenticate() in setUp() after creating test data
        - DO NOT use rest_framework.authtoken - this project uses JWT
        - DO NOT use Token.objects.create() - use the login endpoint

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
                # Check if AI returned instructions instead of code
                if self._is_instructions_not_code(content):
                    console.print(f"    [yellow]⚠ AI returned instructions instead of code, retrying...[/yellow]")
                    # Try to generate again with simpler prompt
                    return self._retry_with_simpler_prompt(app_name, app_endpoints, ai_prompt, structured_analysis)

                console.print(
                    f"    [green]✓ Generated {len(content)} chars of test code[/green]"
                )
                return content
        else:
            console.print(f"    [red]✗ AI generation failed after retries[/red]")

        return None

    # FILE WRITING
    @staticmethod
    def _final_sanitize(content: str) -> str:
        """Last-line-of-defense fixes applied at the single write choke point.

        ``_clean_code`` already handles these, but this guards against any code
        path (retries, syntax-fix salvage, partial regenerations) that could let
        a known-fatal pattern slip through to disk. These substitutions are all
        idempotent and safe to re-apply.
        """
        # self.str(x) is not a method — collapse to the builtin str(x).
        content = re.sub(r'self\s*\.\s*str\s*\(', 'str(', content)
        return content

    def _write_test_file(
        self,
        app_name: str,
        content: str,
        file_path: Path,
    ) -> str:
        """Write test file to disk with backup support."""

        content = self._final_sanitize(content)

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

    def _validate_generated_code(self, content: str, app_name: str) -> tuple[bool, str]:
        """
        Validate that the generated code is complete and syntactically correct.

        Returns:
            Tuple of (is_valid, cleaned_content)
        """
        console.print(f"    [dim]→ Validating generated code...[/dim]")

        # Check for basic Python syntax
        try:
            compile(content, f'<test_{app_name}>', 'exec')
        except SyntaxError as e:
            console.print(f"    [red]✗ Syntax error in generated code: {e}[/red]")
            # Try to provide more specific error location
            if hasattr(e, 'lineno'):
                console.print(f"    [red]  Error at line {e.lineno}: {e.msg}[/red]")

            # Attempt to fix the syntax error automatically
            console.print(f"    [yellow]→ Attempting to fix syntax error...[/yellow]")
            fixed_content = self._fix_syntax_error(content, e)

            # Try compiling the fixed code
            try:
                compile(fixed_content, f'<test_{app_name}>', 'exec')
                console.print(f"    [green]✓ Syntax error fixed successfully[/green]")
                return True, fixed_content
            except SyntaxError:
                # Last-ditch: drop trailing junk and keep the longest valid prefix.
                # Only accept it if the salvaged code still has a TestCase + test_ method,
                # otherwise we'd hand back a no-op file that runs zero tests.
                salvaged = self._truncate_to_valid_prefix(content)
                if salvaged and 'TestCase' in salvaged and 'def test_' in salvaged:
                    dropped = content.count('\n') - salvaged.count('\n')
                    console.print(
                        f"    [green]✓ Salvaged by dropping {dropped} trailing line(s)[/green]"
                    )
                    return True, salvaged
                console.print(f"    [red]✗ Could not fix syntax error[/red]")
                return False, content

        # Pattern 2: Unmatched brackets/parentheses
        # (the compile() check above already catches real "missing colon" syntax errors;
        # the previous heuristic regex matched normal dict literals and produced a
        # false-positive warning on every successful app.)
        if content.count('{') != content.count('}'):
            console.print(f"    [yellow]⚠ Unmatched curly braces in code[/yellow]")
        if content.count('[') != content.count(']'):
            console.print(f"    [yellow]⚠ Unmatched square brackets in code[/yellow]")
        if content.count('(') != content.count(')'):
            console.print(f"    [yellow]⚠ Unmatched parentheses in code[/yellow]")

        # Pattern 3: Malformed function definitions
        malformed_def = re.findall(r'def\s+\w+\([^)]*\s*\n\s*[^\s:]', content)
        if malformed_def:
            console.print(f"    [yellow]⚠ Malformed function definitions found - missing colons[/yellow]")

        # Check for required imports
        required_imports = ['from django.test import', 'import json']
        for required in required_imports:
            if required not in content:
                console.print(f"    [yellow]⚠ Missing required import: {required}[/yellow]")

        # Check for TestCase class
        if 'class' not in content or 'TestCase' not in content:
            console.print(f"    [yellow]⚠ No TestCase class found[/yellow]")
            return False, content

        # Check for test methods
        if 'def test_' not in content:
            console.print(f"    [yellow]⚠ No test methods found[/yellow]")
            return False, content

        # Check for strict assertions that might fail due to User model behavior differences
        # Some User models set is_staff/is_superuser automatically based on role
        if 'self.assertFalse(user.is_staff)' in content:
            console.print(f"    [yellow]⚠ Test assumes user.is_staff=False - User model may set this automatically[/yellow]")
        if 'self.assertFalse(user.is_superuser)' in content:
            console.print(f"    [yellow]⚠ Test assumes user.is_superuser=False - User model may set this automatically[/yellow]")

        # Check for relative imports (bad)
        if 'from .models import' in content or 'from .serializers import' in content:
            console.print(f"    [red]✗ Found relative imports - use absolute imports instead[/red]")
            return False, content

        # Check for wrong User import
        if 'from django.contrib.auth.models import User' in content:
            console.print(f"    [red]✗ Found django.contrib.auth.models.User - use custom User model[/red]")
            return False, content

        # REMOVED: Check for incorrect self.str() calls
        # The cleaning function handles this automatically with regex substitutions
        # This validation was causing false positives and skipping valid code
        # The cleaning regex patterns already handle: self.str(, self.str (, self.  str(
        # No need to validate here since it's handled during cleaning

        # Check for force_authenticate (bad)
        if 'force_authenticate' in content:
            console.print(f"    [red]✗ Found force_authenticate - use proper authentication method[/red]")
            return False, content

        # Check for JWT authentication if the project uses JWT
        if self.analysis and self.analysis.auth_type == "JWT":
            if 'client.login(' in content:
                console.print(f"    [yellow]⚠ Found client.login() in JWT project - should use JWT authentication[/yellow]")
            # Check for JWT token handling
            if 'HTTP_AUTHORIZATION' not in content and 'Bearer' not in content:
                console.print(f"    [yellow]⚠ JWT project missing Authorization header handling[/yellow]")
            # Bearer-token (header) auth is the default; cookie support is optional.
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
        return True, content

    def _is_instructions_not_code(self, content: str) -> bool:
        """
        Detect if AI returned instructions instead of actual Python code.

        Returns:
            True if content appears to be instructions, False otherwise
        """
        # Check for patterns that indicate instructions rather than code
        instruction_markers = [
            "Generate only valid Python code",
            "Generate full Python code",
            "Provide full Python code",
            "Write complete code",
            "**Generate**",
            "Generate the code",
            "**Provide**",
            "**Helper Methods**",
            "**Test Requirements**",
            "**5. Test Requirements**",
            "**6. Test Data**",
            "**7. Test Structure**",
            "**End of Instructions**",
            "**Generate the Code**",
            "**7. Output Format**",
            "Begin the response with the code block immediately",
            "Do not include markdown explanations outside the code block",
        ]

        # Check for instruction-like patterns
        has_instruction_markers = any(marker.lower() in content.lower() for marker in instruction_markers)

        # Check for actual Python code patterns (be more specific)
        has_python_code = (
            'import ' in content and (
                'django.test import' in content or
                'from django' in content or
                'from rest_framework' in content
            )
        ) or (
            'def test_' in content  # Look specifically for test methods
        ) or (
            'class ' in content and ('Test' in content or 'TestCase' in content)
        )

        # Check if content ends with instructions instead of code
        lines = content.strip().split('\n')
        last_lines = lines[-10:] if len(lines) >= 10 else lines
        ends_with_instructions = any(marker.lower() in ' '.join(last_lines).lower() for marker in [
            'helper', 'requirements', 'structure', 'data', 'end of',
            'begin the response', 'code block', 'markdown explanations'
        ])

        # Check if content is too long for instructions but has no code (highly suspicious)
        is_long_without_code = len(content) > 10000 and not has_python_code

        # If has instruction markers, ends with instructions, is long without code, and no real Python code, it's instructions
        return (has_instruction_markers or ends_with_instructions or is_long_without_code) and not has_python_code

    def _retry_with_simpler_prompt(
        self,
        app_name: str,
        app_endpoints: list[EndpointInfo],
        ai_prompt: str,
        structured_analysis: dict
    ) -> str | None:
        """
        Retry AI generation with a simpler prompt focused on getting code.

        Returns:
            Generated test code or None
        """
        # Build a much more direct prompt that demands code only
        simpler_prompt = f"""You are a Python code generator. Generate Django test code ONLY.

Application: {app_name}

Do not write explanations, instructions, or guidance. Do not use markdown formatting.

Start your response immediately with:
```python
from django.test import TestCase
```

Generate a complete Django test file with:
1. Import statements (from django.test import, import json, etc.)
2. Test classes that inherit from TestCase
3. Test methods (def test_*) with proper assertions
4. setUp and tearDown methods as needed

Test these endpoints:
"""
        # Add endpoint list for context
        for ep in app_endpoints[:5]:  # Limit to first 5 to keep prompt concise
            simpler_prompt += f"- {', '.join(ep.http_methods)} {ep.url_pattern}\n"

        simpler_prompt += """

REQUIREMENTS:
- Use absolute imports: from apps.{app_name}.models import ModelName
- Use get_user_model() for User model
- Handle JWT authentication: self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
- Convert UUIDs to strings in URLs
- Write working, executable Python code
- CRITICAL: Ensure all parentheses, brackets, and braces are matched
- CRITICAL: Use consistent indentation (4 spaces per level)

END OF INSTRUCTIONS. OUTPUT CODE ONLY."""

        # Build system prompt for retry
        retry_system_prompt = """You are a Python code generator. Output ONLY valid Python code.
CRITICAL RULES:
1. Complete all methods with proper closing parentheses
2. Use consistent indentation (4 spaces per level)
3. Never leave unmatched parentheses, brackets, or braces
4. Return ONLY Python code, no markdown, no explanation
"""

        # Call AI with retry prompt
        console.print(f"    [dim]Calling AI model with retry prompt...[/dim]")
        response = self.ai_helper.call_with_retry(
            model=self.ai_helper.MODEL,
            max_tokens=self.MAX_TOKENS,
            messages=[
                {"role": "system", "content": retry_system_prompt},
                {"role": "user", "content": simpler_prompt},
            ],
        )

        if response and response.choices and response.choices[0].message.content:
            content = response.choices[0].message.content
            console.print(f"    [green]✓ Retry generated {len(content)} chars of test code[/green]")
            return content
        else:
            console.print(f"    [red]✗ Retry AI generation failed[/red]")
            return None

    def _fix_syntax_error(self, content: str, error: SyntaxError) -> str:
        """
        Attempt to fix syntax errors in generated code.

        Args:
            content: The generated code with syntax errors
            error: The SyntaxError object

        Returns:
            Fixed code (may still have errors)
        """
        lines = content.split('\n')
        line_num = error.lineno if hasattr(error, 'lineno') else 0

        # Fix specific patterns based on error message
        if "unmatched ')'" in str(error).lower() or "unmatched '('" in str(error).lower():
            # Find and fix unmatched parentheses
            lines[line_num - 1] = self._fix_line_parens(lines[line_num - 1])
        elif "unexpected indent" in str(error).lower():
            # Fix indentation issues
            lines = self._fix_indentation(lines, line_num)
        elif "invalid syntax" in str(error).lower():
            # Try to fix various syntax issues
            lines[line_num - 1] = self._fix_invalid_syntax(lines[line_num - 1])

        return '\n'.join(lines)

    def _fix_line_parens(self, line: str) -> str:
        """Fix unmatched parentheses in a line."""
        # Fix 1: Missing closing parenthesis before quote in f-string
        if 'f\'' in line or 'f"' in line:
            # Pattern: f'/path/{str(id)}' -> f'/path/{str(id)})'
            # Check for unclosed str() calls in f-strings
            line = re.sub(r"f['\"]([^{\'\"]]*{str\([^)]+\)(?!\))", lambda m: m.group(0) + ")" if m.group(0).count('(') > m.group(0).count(')') else m.group(0), line)

        # Fix 2: Missing closing parenthesis before quote
        # Pattern: method('arg' -> method('arg')
        line = re.sub(r"(\w+)\('([^']*)'(?!\))", r"\1('\2')", line)
        line = re.sub(r'(\w+)\("([^"]*)"(?!\))', r'\1("\2")', line)

        # Fix 3: Add missing closing parentheses at end of line
        open_count = line.count('(')
        close_count = line.count(')')
        if open_count > close_count:
            # Add missing closing parentheses
            line += ')' * (open_count - close_count)

        # Fix 4: Fix str() calls that are missing closing parenthesis
        # Pattern: str(something' -> str(something)'
        line = re.sub(r'str\(([^)]*)\'$', r'str(\1)\'', line)
        line = re.sub(r'str\(([^)]*)"$', r'str(\1)"', line)

        return line

    def _fix_invalid_syntax(self, line: str) -> str:
        """Fix invalid syntax in a line."""
        # Fix 1: Missing colon after function definition
        if re.search(r'def\s+\w+\([^)]*\)\s*$', line):
            return line + ':'

        # Fix 2: Missing colon in dictionary
        if re.search(r'\{\s*\w+\s*[^:,\s\}]', line):
            # Find where colon should be added
            line = re.sub(r'(\{\s*\w+\s*)([^:,\s\}])', r'\1: \2', line)

        return line

    def _fix_indentation(self, lines: list[str], error_line: int) -> list[str]:
        """
        Fix indentation issues in generated code.

        Args:
            lines: List of code lines
            error_line: Line number where error occurred (1-indexed)

        Returns:
            Fixed list of lines
        """
        if error_line < 1 or error_line > len(lines):
            return lines

        # Determine expected indentation level
        # Look at the previous line to understand the context
        prev_line = lines[error_line - 2] if error_line > 1 else ""
        current_line = lines[error_line - 1]

        # Case 1: Previous line ends with colon, so we expect increased indentation
        if prev_line.rstrip().endswith(':'):
            # Calculate the expected indent (4 spaces or 1 tab per level)
            prev_indent = len(prev_line) - len(prev_line.lstrip())
            expected_indent = prev_indent + 4  # Add 4 spaces for next level
            current_indent = len(current_line) - len(current_line.lstrip())

            # If current line has less indentation than expected, fix it
            if current_indent < expected_indent:
                # Add the missing indentation
                lines[error_line - 1] = ' ' * (expected_indent - current_indent) + current_line

        # Case 2: Line is at same level as class/method definition but shouldn't be
        elif re.match(r'^\s*(class|def)\s+', prev_line):
            # This line should be indented (it's inside the class/method)
            prev_indent = len(prev_line) - len(prev_line.lstrip())
            current_indent = len(current_line) - len(current_line.lstrip())

            if current_indent <= prev_indent:
                # This line should be indented more
                lines[error_line - 1] = '    ' + current_line  # Add 4 spaces

        # Case 3: Fix mixed tabs and spaces
        if '\t' in current_line:
            # Convert tabs to spaces (4 spaces per tab)
            lines[error_line - 1] = current_line.replace('\t', '    ')

        return lines

    def _normalize_indentation(self, content: str) -> str:
        """
        Normalize indentation in generated code.

        Args:
            content: The code to normalize

        Returns:
            Code with normalized indentation
        """
        lines = content.split('\n')
        normalized_lines = []

        # Track the expected indentation level
        indent_stack = [0]  # Stack of expected indentation levels (in spaces)

        for line in lines:
            stripped = line.lstrip()
            if not stripped:
                # Keep empty lines as-is
                normalized_lines.append(line)
                continue

            # Calculate current indentation
            current_indent = len(line) - len(stripped)
            leading_whitespace = line[:current_indent]

            # Check for mixed tabs and spaces
            if '\t' in leading_whitespace and ' ' in leading_whitespace:
                # Convert tabs to spaces (4 spaces per tab)
                leading_whitespace = leading_whitespace.replace('\t', '    ')
                line = leading_whitespace + stripped

            # Check if line starts a new block (ends with colon)
            if stripped.rstrip().endswith(':'):
                # This line defines a new block
                # Ensure its indentation matches the current level
                expected_indent = indent_stack[-1]
                if current_indent != expected_indent:
                    # Fix the indentation
                    line = ' ' * expected_indent + stripped
                    normalized_lines.append(line)
                else:
                    normalized_lines.append(line)

                # Push new indent level for next lines
                indent_stack.append(expected_indent + 4)
            elif stripped.startswith(('return ', 'raise ', 'yield ', 'break ', 'continue ')) or \
                 stripped.startswith(('assert ', 'pass ')):
                # These statements should be at the same level as the block
                if len(indent_stack) > 1:
                    expected_indent = indent_stack[-2]  # Use parent level
                    if current_indent < expected_indent:
                        # This line is dedented, pop the stack
                        indent_stack.pop()
                        expected_indent = indent_stack[-1]

                    if current_indent != expected_indent:
                        line = ' ' * expected_indent + stripped
                normalized_lines.append(line)
            else:
                # Regular line - ensure indentation is at least at current level
                expected_indent = indent_stack[-1]
                if current_indent < expected_indent and not stripped.startswith('#'):
                    # Line is less indented than expected, might be dedent
                    # Try to find matching level in stack
                    while len(indent_stack) > 1 and current_indent < indent_stack[-1]:
                        indent_stack.pop()
                    expected_indent = indent_stack[-1]

                if current_indent < expected_indent and not stripped.startswith('#'):
                    # Fix under-indented line
                    line = ' ' * expected_indent + stripped

                normalized_lines.append(line)

        return '\n'.join(normalized_lines)

    def _ensure_user_defined(self, content: str) -> str:
        """Guarantee the ``User`` symbol exists when the test references it.

        If the generated code uses ``User`` (e.g. ``User.objects.create_user``)
        but never imports or assigns it, inject the standard
        ``User = get_user_model()`` definition just after the import block so the
        module doesn't blow up with NameError at runtime.
        """
        uses_user = re.search(r'\bUser\b\s*[.(]', content)
        if not uses_user:
            return content

        # Already defined? (assignment, or imported as a name)
        if re.search(r'^\s*User\s*=', content, re.MULTILINE):
            return content
        if re.search(r'^\s*from\s+\S+\s+import\s+.*\bUser\b', content, re.MULTILINE):
            return content

        lines = content.split('\n')
        # Find the last top-level import line to insert after.
        insert_at = 0
        for i, line in enumerate(lines):
            if re.match(r'^\s*(import\s+\S+|from\s+\S+\s+import\s+)', line):
                insert_at = i + 1

        injection = [
            'from django.contrib.auth import get_user_model',
            'User = get_user_model()',
        ]
        lines[insert_at:insert_at] = injection
        return '\n'.join(lines)

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

        # Fix incorrect User imports - replace bad patterns with correct ones
        # Pattern 1: from apps.user import User -> from apps.user.models import User
        content = re.sub(r'from apps\.(\w+) import User', r'from apps.\1.models import User', content)
        # Pattern 2: from apps.user.models.models import User -> from apps.user.models import User
        content = re.sub(r'from apps\.(\w+)\.models\.models import User', r'from apps.\1.models import User', content)
        # Pattern 3: from apps.user.models import User (keep this - it's correct)
        # Pattern 4: from django.contrib.auth.models import User -> get_user_model()
        content = re.sub(
            r'from django\.contrib\.auth\.models import User',
            'from django.contrib.auth import get_user_model\nUser = get_user_model()',
            content
        )

        # Fix wrong import patterns for models
        # Pattern: from apps.<app> import <Model> -> from apps.<app>.models import <Model>
        content = re.sub(r'from apps\.(\w+) import (?!User|get_user_model)', r'from apps.\1.models import ', content)

        # Validate every `from apps.<x>...` against the actually-installed apps. AI models
        # routinely hallucinate names (apps.team vs apps.teams, apps.category that doesn't
        # exist at all). A single bad import ImportErrors the whole test module, so we try
        # singular/plural variants first and drop the line as a last resort.
        content = self._fix_hallucinated_app_imports(content)

        # Only rewrite get_user_model() to a direct import for projects that
        # actually have a custom apps.* user model. For stock-User projects
        # (django.contrib.auth) get_user_model() is correct — rewriting it to
        # `from apps.user.models import User` would import a module that doesn't
        # exist and break the whole test file.
        auth_module = self.analysis.auth_module if self.analysis else None
        if auth_module and auth_module.startswith("apps."):
            user_module = auth_module if auth_module.endswith(".models") else f"{auth_module}.models"
            content = re.sub(
                r'from django\.contrib\.auth import get_user_model\nUser = get_user_model\(\)',
                f'from {user_module} import User',
                content,
            )

        # Ensure the User model is defined when referenced. Weaker models
        # sometimes use User.objects / User(...) without importing or defining
        # it, which raises NameError in every test. Inject the standard
        # get_user_model() definition right after the imports if it's missing.
        content = self._ensure_user_defined(content)

        # Fix reverse() calls - replace with direct URL paths
        # reverse('app:name') -> '/api/app/name/'
        content = re.sub(r"reverse\(['\"]apply:(\w+)['\"]\)", r"'/api/application/\1/'", content)
        content = re.sub(r"reverse\(['\"]enquiry:(\w+)['\"]\)", r"'/api/enquiry/\1/'", content)
        content = re.sub(r"reverse\(['\"]user:(\w+)['\"]\)", r"'/api/user/\1/'", content)
        content = re.sub(r"reverse\(['\"]gallery:(\w+)['\"]\)", r"'/api/gallery/\1/'", content)
        content = re.sub(r"reverse\(['\"]notices:(\w+)['\"]\)", r"'/api/notices/\1/'", content)
        content = re.sub(r"reverse\(['\"]calender:(\w+)['\"]\)", r"'/api/calendar/\1/'", content)
        content = re.sub(r"reverse\(['\"]downloads:(\w+)['\"]\)", r"'/api/downloads/\1/'", content)
        content = re.sub(r"reverse\(['\"]teams:(\w+)['\"]\)", r"'/api/teams/\1/'", content)
        content = re.sub(r"reverse\(['\"]dashboard:(\w+)['\"]\)", r"'/api/dashboard/\1/'", content)
        content = re.sub(r"reverse\(['\"]analytics:(\w+)['\"]\)", r"'/api/analytics/\1/'", content)
        
        # Handle reverse with args - replace with URL patterns
        content = re.sub(r"reverse\(['\"]apply:(\w+)['\"], args=\[(\w+)\]\)", r"'/api/application/\1/{\2}/'", content)
        content = re.sub(r"reverse\(['\"]enquiry:(\w+)['\"], args=\[(\w+)\]\)", r"'/api/enquiry/\1/{\2}/'", content)
        content = re.sub(r"reverse\(['\"]user:(\w+)['\"], args=\[(\w+)\]\)", r"'/api/user/\1/{\2}/'", content)
        
        # Handle reverse with kwargs
        content = re.sub(r"reverse\(['\"]apply:(\w+)['\"], kwargs=\{(\w+): (\w+)\}\)", r"'/api/application/\1/{\3}/'", content)

        # Fix wrong authentication imports/typos
        content = re.sub(r'from rest_framework\.autenfication', 'from rest_framework.authentication', content)
        content = re.sub(r'from rest_framework\.authtoken', '# rest_framework.authtoken not used', content)
        
        # Normalise mistaken token endpoints to the project's DETECTED login URL.
        login_url = (
            self.analysis.login_url
            if self.analysis and self.analysis.login_url
            else "/api/user/login/"
        )
        content = re.sub(r"client\.post\(['\"]/api/auth/token/['\"]", f"client.post('{login_url}'", content)
        content = re.sub(r"client\.post\(['\"]/api/token/['\"]", f"client.post('{login_url}'", content)

        # Normalise login/token POSTs to the ProjectAnalyzer-detected login URL.
        # The app-level detector sometimes drops the URL include prefix
        # (e.g. '/auth/login/' instead of '/api/auth/login/').
        if self.analysis and self.analysis.login_url:
            content = re.sub(
                r"self\.client\.post\(\s*f?['\"][^'\"]*(?:login|/token)[^'\"]*['\"]",
                f"self.client.post('{self.analysis.login_url}'",
                content,
            )

        # Ensure every client request URL ends with a trailing slash. Django's
        # APPEND_SLASH returns a 301 redirect (not the real response) when a
        # slash-terminated route is requested without the slash, which makes
        # every assertion fail. Handles plain and f-strings, both quote styles.
        def _ensure_trailing_slash(m: re.Match) -> str:
            prefix, quote, body = m.group(1), m.group(2), m.group(3)
            if not body or body.endswith("/") or "?" in body:
                return m.group(0)
            return f"{prefix}{body}/{quote}"

        content = re.sub(
            r"(self\.client\.(?:get|post|put|patch|delete)\(\s*f?(['\"]))([^'\"]*)\2",
            _ensure_trailing_slash,
            content,
        )

        # Fix user creation - custom email-based User models use 'full_name' not 'name'.
        # Only apply to those projects; a stock User has neither field.
        if self.analysis and self.analysis.username_field == "email":
            content = re.sub(r"'name':\s*'Test User'", "'full_name': 'Test User'", content)
            content = re.sub(r"'name':\s*'[^']*'", lambda m: m.group(0).replace("'name':", "'full_name':"), content)

        # Strip 'username' from generated tests when the project's User model doesn't have it.
        # ProjectAnalyzer detects the real User fields; if 'username' isn't there, the AI's
        # default habit of including it will crash create_user() with TypeError.
        if (
            self.analysis
            and self.analysis.safe_user_fields
            and 'username' not in self.analysis.safe_user_fields
        ):
            # Dict-literal form on its own line: 'username': 'value', (or double-quoted, with/without trailing comma)
            content = re.sub(
                r"^[ \t]*['\"]username['\"]\s*:\s*[^\n]*?,?[ \t]*\n",
                "",
                content,
                flags=re.MULTILINE,
            )
            # Keyword-arg form inside a call: username='value', or username="value",
            content = re.sub(
                r"\busername\s*=\s*['\"][^'\"]*['\"]\s*,?\s*",
                "",
                content,
            )

        # Fix incorrect self.str() calls - replace with proper str() conversion
        # Handle various patterns:
        # 1. self.str(user.id) -> str(self.user.id)
        # 2. self.str(page.id) -> str(self.page.id)
        # 3. self.str(application.id) -> str(self.application.id)
        # 4. self.str(enquiry.id) -> str(self.enquiry.id)
        # 5. self.str(regular_user.id) -> str(self.regular_user.id)
        content = re.sub(r"self\.str\(self\.(\w+)\.(\w+)\)", r"str(self.\1.\2)", content)  # self.str(self.user.id) -> str(self.user.id)
        content = re.sub(r'self\.str\((\w+)\.(\w+)\)', r'str(self.\1.\2)', content)  # self.str(user.id) -> str(self.user.id)
        content = re.sub(r'self\.str\((self\.\w+)\.id\)', r'str(\1.id)', content)  # self.str(self.regular_user.id) -> str(self.regular_user.id)
        content = re.sub(r'self\.str\(', r'str(', content)  # self.str( -> str( (remaining cases)

        # Fix force_authenticate usage - replace with proper authentication
        # For JWT projects, replace with JWT authentication pattern
        if self.analysis and self.analysis.auth_type == "JWT":
            # Try to replace force_authenticate with JWT authentication
            content = re.sub(
                r'self\.client\.force_authenticate\(user=self\.test_user\)',
                'self.authenticate_jwt(self.test_user.email, "Str0ng!Pass99")',
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
                'self.client.login(email=self.test_user.email, password="Str0ng!Pass99")',
                content
            )
            content = re.sub(
                r'self\.client\.force_authenticate\([^)]+\)',
                '# Note: Use client.login() for authentication',
                content
            )

        # Fix PIL Image.save() format issues - common AI mistake
        # Pattern: image.save(file, 'jpg') -> image.save(file, 'JPEG')
        # Pattern: image.save(file, 'JPG') -> image.save(file, 'JPEG')
        # Pattern: image.save(file, 'png') -> image.save(file, 'PNG')
        content = re.sub(
            r"image\.save\(file,\s*['\"](jpg|jpeg)['\"]",
            r"image.save(file, 'JPEG')",
            content,
            flags=re.IGNORECASE
        )
        content = re.sub(
            r"image\.save\(file,\s*['\"](png)['\"]",
            r"image.save(file, 'PNG')",
            content,
            flags=re.IGNORECASE
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

        # Validate basic Python syntax. If broken, try to salvage by truncating from
        # the end of the file backwards until we find a valid prefix. AI outputs often
        # have trailing junk (stray prose, fence markers, an unfinished test) — keeping
        # the valid prefix is far safer than the previous "balance brackets" heuristic,
        # which appended `)` to every multi-line call and silently broke valid code.
        try:
            compile(content, '<string>', 'exec')
        except SyntaxError as e:
            console.print(f"    [yellow]⚠ Syntax warning in generated code: {e}[/yellow]")
            salvaged = self._truncate_to_valid_prefix(content)
            if salvaged is not None and salvaged.strip() != content.strip():
                dropped = content.count('\n') - salvaged.count('\n')
                console.print(
                    f"    [dim]→ Salvaged code by dropping {dropped} trailing line(s)[/dim]"
                )
                content = salvaged

        return content

    def _truncate_to_valid_prefix(self, content: str) -> str | None:
        """
        Find the longest leading prefix of `content` that parses as Python.

        Walks backwards from the end of the file, dropping one line at a time, until
        compile() succeeds. Returns the salvaged prefix, or None if no prefix parses
        (in which case the caller keeps the original).
        """
        lines = content.split('\n')
        for end in range(len(lines), 0, -1):
            candidate = '\n'.join(lines[:end])
            try:
                compile(candidate, '<truncate>', 'exec')
                return candidate
            except SyntaxError:
                continue
        return None

    def _fix_hallucinated_app_imports(self, content: str) -> str:
        """
        Rewrite or drop `from apps.<x>...` lines that name an app that isn't installed.

        Strategy:
        1. If <x> is a real installed app, leave the line alone.
        2. Try simple singular/plural variants (team↔teams, category↔categories).
        3. If no variant matches, comment the line out so the rest of the module still
           imports — the test methods that needed those symbols will fail individually
           rather than blocking the entire file with ImportError.
        """
        if not self.app_module_map:
            return content

        valid = set(self.app_module_map.keys())

        def variants(name: str) -> list[str]:
            cands: list[str] = []
            if name.endswith('ies'):
                cands.append(name[:-3] + 'y')      # categories -> category
            if name.endswith('y'):
                cands.append(name[:-1] + 'ies')    # category -> categories
            if name.endswith('s') and len(name) > 1:
                cands.append(name[:-1])            # teams -> team
            cands.append(name + 's')               # team -> teams
            return cands

        import_re = re.compile(r'^(\s*)from apps\.(\w+)(\.\w+)?\s+import\s+(.+)$')
        out_lines: list[str] = []
        rewritten: dict[str, str] = {}
        dropped: list[str] = []

        for line in content.split('\n'):
            m = import_re.match(line)
            if not m:
                out_lines.append(line)
                continue
            indent, app_name, submodule, imports = m.groups()
            if app_name in valid:
                out_lines.append(line)
                continue
            match = next((v for v in variants(app_name) if v in valid), None)
            if match:
                rewritten[app_name] = match
                out_lines.append(
                    f"{indent}from apps.{match}{submodule or '.models'} import {imports}"
                )
            else:
                dropped.append(line.strip())
                out_lines.append(f"{indent}# DjangoProbe: dropped hallucinated import: {line.strip()}")

        if rewritten:
            for bad, good in rewritten.items():
                console.print(f"    [dim]Rewrote import: apps.{bad} → apps.{good}[/dim]")
        if dropped:
            console.print(f"    [yellow]⚠ Dropped {len(dropped)} hallucinated import(s)[/yellow]")

        return '\n'.join(out_lines)


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
