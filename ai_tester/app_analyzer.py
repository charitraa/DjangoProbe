import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any
from rich.console import Console
from ai_tester.ai_helper import AIHelper
from ai_tester.django_specific_analyzer import DjangoSpecificAnalyzer

console = Console()


class AppAnalyzer:
    """
    Deeply analyzes a Django app and generates AI-powered prompts for test generation.

    This module:
    1. Reads and parses models.py, serializers.py, views.py, urls.py
    2. Uses AI to analyze the code structure
    3. Generates a custom prompt with all necessary details for test generation
    4. Returns structured analysis + AI-generated prompt

    Usage:
        analyzer = AppAnalyzer(repo_path, ai_helper)
        analysis, prompt = analyzer.analyze_app(app_name, app_endpoints)
    """

    MAX_TOKENS = 8192  # Maximum tokens for AI analysis
    ANALYSIS_DIR = Path.home() / ".djangoprobe" / "analysis"  # Directory for saving analysis files


    def __init__(self, repo_path: str, ai_helper: AIHelper):
        self.repo_path = Path(repo_path)
        self.ai_helper = ai_helper
        # Create analysis directory if it doesn't exist
        self.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    def _should_skip(self, path: Path) -> bool:
        """Check if a path should be skipped during scanning."""
        skip = {"venv", "env", "site-packages", "__pycache__", ".git", "node_modules"}
        return any(p in path.parts for p in skip)

    def _save_analysis_to_file(self, app_name: str, analysis: Dict[str, Any], file_type: str = "analysis") -> Path:
        """
        Save analysis data to a JSON file.

        Args:
            app_name: Name of the app being analyzed
            analysis: The analysis data to save
            file_type: Type of file ('analysis', 'ai_input', 'ai_output')

        Returns:
            Path: The path to the saved file
        """
        # Create app-specific directory
        app_dir = self.ANALYSIS_DIR / app_name
        app_dir.mkdir(exist_ok=True)

        # Determine filename based on type
        if file_type == "analysis":
            filename = "analysis.json"
        elif file_type == "ai_input":
            filename = "ai_input.txt"
        elif file_type == "ai_output":
            filename = "ai_output.txt"
        else:
            filename = f"{file_type}.json"

        file_path = app_dir / filename

        if file_type == "ai_input":
            # Save AI input as text file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(analysis))
        elif file_type == "ai_output":
            # Save AI output as text file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(analysis))
        else:
            # Save analysis as JSON
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, default=str)

        return file_path

    def analyze_app(self, app_name: str, app_endpoints: List) -> tuple[Dict[str, Any], str]:
        """
        Analyze a Django app and generate AI-powered prompt for test generation.

        Returns:
            tuple: (analysis_dict, ai_generated_prompt)
        """
        console.print(f"\n  [bold cyan]Analyzing app:[/bold cyan] {app_name}")

        app_dir = self.ai_helper.get_app_dir(app_name)
        if not app_dir:
            console.print(f"  [red]✗ App dir not found: {app_name}[/red]")
            return {}, ""

        # Collect raw source code from app files
        source_code = self._collect_app_source_code(app_dir)

        # Initialize structured analysis dictionary
        structured_analysis = {}

        # DJANGO-SPECIFIC: Analyze Django project configuration
        console.print(f"    [dim]→ Analyzing Django project...[/dim]")
        django_analyzer = DjangoSpecificAnalyzer(str(self.repo_path), source_code)
        django_project_analysis = django_analyzer.analyze_django_project()
        structured_analysis["django_project"] = django_project_analysis

        console.print(f"    [cyan]✓ Django version:[/cyan] {django_project_analysis['django_version']}")
        console.print(f"    [cyan]✓ DRF installed:[/cyan] {django_project_analysis['rest_framework_config']['installed']}")
        console.print(f"    [cyan]✓ Auth backends:[/cyan] {len(django_project_analysis['authentication_settings']['auth_backends'])}")

        # DRF-specific view analysis
        if "views" in source_code:
            console.print(f"    [dim]→ Analyzing DRF views...[/dim]")
            drf_views_analysis = django_analyzer.analyze_drf_views()
            structured_analysis["drf_views"] = drf_views_analysis

            viewset_count = len(drf_views_analysis["viewsets"])
            api_view_count = len(drf_views_analysis["api_views"])
            console.print(f"    [cyan]✓ ViewSets:[/cyan] {viewset_count}, APIViews: {api_view_count}")

        # Parse and extract structured information
        structured_analysis.update(self._parse_app_structure(app_dir, source_code, app_endpoints))

        # ENHANCED: Detect authentication method and response structure
        console.print(f"    [dim]→ Detecting authentication method...[/dim]")
        auth_info = self._detect_auth_method(source_code, app_dir)
        structured_analysis["auth_info"] = auth_info

        console.print(f"    [dim]→ Detecting response structure...[/dim]")
        response_structure = self._detect_response_structure(source_code)
        structured_analysis["response_structure"] = response_structure

        console.print(f"    [dim]→ Extracting URL parameters...[/dim]")
        url_params = self._extract_url_parameters(source_code)
        structured_analysis["url_parameters"] = url_params

        console.print(f"    [dim]→ Analyzing permission classes...[/dim]")
        permission_analysis = self._analyze_permission_classes(source_code, app_dir)
        structured_analysis["permission_analysis"] = permission_analysis

        # Build auth_response_structure for compatibility with existing code
        auth_response_structure = self._build_auth_response_structure(auth_info, response_structure)
        structured_analysis["auth_response_structure"] = auth_response_structure

        # Print detection results
        console.print(f"    [cyan]✓ Auth method:[/cyan] {auth_info['method']}")
        console.print(f"    [cyan]✓ Response structure:[/cyan] {response_structure['structure_type']}")
        if url_params:
            console.print(f"    [cyan]✓ URL parameters found:[/cyan] {len(url_params)} views")
        if permission_analysis:
            console.print(f"    [cyan]✓ Permission classes analyzed:[/cyan] {len(permission_analysis)}")

        # Save the analysis data to file
        analysis_file = self._save_analysis_to_file(app_name, structured_analysis, "analysis")
        console.print(f"    [dim]✓ Analysis saved to:[/dim] {analysis_file}")

        # Generate AI-powered prompt using the analysis
        ai_prompt = self._generate_ai_prompt(app_name, structured_analysis, source_code)

        return structured_analysis, ai_prompt

    def _collect_app_source_code(self, app_dir: Path) -> Dict[str, str]:
        """
        Collect source code from all relevant files in the app.
        """
        source_code = {}

        # Priority files
        priority_files = {
            "models.py": "models",
            "serializers.py": "serializers",
            "views.py": "views",
            "urls.py": "urls",
        }

        # Read priority files
        for filename, key in priority_files.items():
            file_path = app_dir / filename
            if file_path.exists():
                content = file_path.read_text(errors="ignore")
                source_code[key] = content
                console.print(
                    f"    [dim]Read:[/dim] {app_dir.name}/{filename} "
                    f"[dim]({len(content)} chars)[/dim]"
                )

        # Read secondary files if they exist
        secondary_files = {
            "permissions.py": "permissions",
            "filters.py": "filters",
            "forms.py": "forms",
            "services.py": "services",
        }

        for filename, key in secondary_files.items():
            file_path = app_dir / filename
            if file_path.exists():
                content = file_path.read_text(errors="ignore")
                source_code[key] = content
                console.print(
                    f"    [dim]Read:[/dim] {app_dir.name}/{filename} "
                    f"[dim]({len(content)} chars)[/dim]"
                )

        return source_code

    def _parse_app_structure(
        self,
        app_dir: Path,
        source_code: Dict[str, str],
        app_endpoints: List
    ) -> Dict[str, Any]:
        """
        Parse and extract structured information from app files.

        Returns a dictionary with:
        - models: List of models with their fields
        - serializers: List of serializers with their fields
        - views: List of views with their methods and permissions
        - endpoints: List of endpoints with HTTP methods
        - relationships: ForeignKey and ManyToMany relationships
        """
        analysis = {
            "app_name": app_dir.name,
            "models": [],
            "serializers": [],
            "views": [],
            "endpoints": [],
            "relationships": {
                "foreign_keys": [],
                "many_to_many": [],
            },
            "auth_requirements": [],
        }

        # Parse models
        if "models" in source_code:
            analysis["models"] = self._parse_models(source_code["models"])

        # Parse serializers
        if "serializers" in source_code:
            analysis["serializers"] = self._parse_serializers(source_code["serializers"])

        # Parse views
        if "views" in source_code:
            analysis["views"] = self._parse_views(source_code["views"])

        # Extract endpoints
        analysis["endpoints"] = [
            {
                "url": ep.url_pattern,
                "methods": ep.http_methods,
                "view": ep.view_name,
                "requires_auth": ep.requires_auth,
            }
            for ep in app_endpoints
        ]

        # Extract relationships
        analysis["relationships"] = self._extract_relationships(analysis["models"])

        # Extract auth requirements
        analysis["auth_requirements"] = self._extract_auth_requirements(analysis["views"])

        return analysis

    def _detect_settings_module(self) -> str | None:
        """
        Detect the Django settings module for the project.

        Scans the project to find settings.py and constructs the proper
        Python module path based on the directory structure.

        Returns:
            str: The settings module path (e.g., 'usea.settings') or None
        """
        # Find all settings.py files
        settings_files = list(self.repo_path.rglob("settings.py"))

        # Filter out venv and other non-project settings
        for settings_file in settings_files:
            if self._should_skip(settings_file):
                continue

            # Get the relative path from repo root
            try:
                relative = settings_file.relative_to(self.repo_path)
            except ValueError:
                # Not within repo path, skip
                continue

            # Convert path to module path
            parts = list(relative.parts[:-1])  # Remove 'settings.py'
            module_path = ".".join(parts) + ".settings"

            # Verify this looks like a valid settings module
            # by checking for common Django settings patterns
            try:
                content = settings_file.read_text(errors="ignore")
                if "INSTALLED_APPS" in content or "SECRET_KEY" in content:
                    return module_path
            except Exception:
                pass

        return None

    def _parse_models(self, source: str) -> List[Dict[str, Any]]:
        """
        Parse models.py and extract model information.
        """
        models = []
        try:
            tree = ast.parse(source)
        except Exception as e:
            console.print(f"    [yellow]⚠ Failed to parse models.py: {e}[/yellow]")
            return models

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                model_info = {
                    "name": node.name,
                    "fields": [],
                    "meta": {},
                }

                # Extract Meta class
                for item in node.body:
                    if isinstance(item, ast.ClassDef) and item.name == "Meta":
                        for meta_item in item.body:
                            if isinstance(meta_item, ast.Assign):
                                for target in meta_item.targets:
                                    if isinstance(target, ast.Name):
                                        model_info["meta"][target.id] = ast.unparse(
                                            meta_item.value
                                        )

                # Extract fields
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                                field_info = {
                                    "name": target.id,
                                    "type": self._get_field_type(item),
                                    "required": self._is_field_required(item),
                                    "default": self._get_field_default(item),
                                    "choices": self._get_field_choices(item),
                                }
                                model_info["fields"].append(field_info)

                if model_info["fields"]:
                    models.append(model_info)

        return models

    def _parse_serializers(self, source: str) -> List[Dict[str, Any]]:
        """
        Parse serializers.py and extract serializer information.
        """
        serializers = []
        try:
            tree = ast.parse(source)
        except Exception as e:
            console.print(f"    [yellow]⚠ Failed to parse serializers.py: {e}[/yellow]")
            return serializers

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                serializer_info = {
                    "name": node.name,
                    "fields": [],
                    "model": None,
                }

                # Check if it's a ModelSerializer
                for base in node.bases:
                    base_str = ast.unparse(base)
                    if "ModelSerializer" in base_str:
                        serializer_info["is_model_serializer"] = True
                        # Try to extract Meta.model
                        for item in node.body:
                            if isinstance(item, ast.ClassDef) and item.name == "Meta":
                                for meta_item in item.body:
                                    if isinstance(meta_item, ast.Assign):
                                        for target in meta_item.targets:
                                            if (
                                                isinstance(target, ast.Name)
                                                and target.id == "model"
                                            ):
                                                serializer_info["model"] = ast.unparse(
                                                    meta_item.value
                                                )

                # Extract fields
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                                field_info = {
                                    "name": target.id,
                                    "type": self._get_field_type(item),
                                    "required": self._is_field_required(item),
                                    "read_only": self._is_read_only_field(item),
                                }
                                serializer_info["fields"].append(field_info)

                if serializer_info["fields"]:
                    serializers.append(serializer_info)

        return serializers

    def _parse_views(self, source: str) -> List[Dict[str, Any]]:
        """
        Parse views.py and extract view information.
        """
        views = []
        try:
            tree = ast.parse(source)
        except Exception as e:
            console.print(f"    [yellow]⚠ Failed to parse views.py: {e}[/yellow]")
            return views

        for node in ast.walk(tree):
            # Class-based views
            if isinstance(node, ast.ClassDef):
                view_info = {
                    "name": node.name,
                    "type": "class_based",
                    "methods": [],
                    "permissions": [],
                    "base_classes": [ast.unparse(b) for b in node.bases],
                }

                # Extract HTTP methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_name = item.name.lower()
                        if method_name in [
                            "get",
                            "post",
                            "put",
                            "patch",
                            "delete",
                            "head",
                            "options",
                        ]:
                            view_info["methods"].append(method_name.upper())

                # Extract permission_classes
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "permission_classes":
                                view_info["permissions"] = self._extract_permission_classes(
                                    item.value
                                )

                if view_info["methods"]:
                    views.append(view_info)

            # Function-based views
            elif isinstance(node, ast.FunctionDef):
                view_info = {
                    "name": node.name,
                    "type": "function_based",
                    "methods": [],
                    "permissions": [],
                }

                # Extract HTTP methods from @api_view decorator
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        call_name = ast.unparse(decorator.func)
                        if "api_view" in call_name:
                            if decorator.args:
                                arg = decorator.args[0]
                                if isinstance(arg, ast.List):
                                    view_info["methods"] = [
                                        elt.value.upper()
                                        for elt in arg.elts
                                        if isinstance(elt, ast.Constant)
                                    ]

                # Extract @permission_classes decorator
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        call_name = ast.unparse(decorator.func)
                        if "permission_classes" in call_name:
                            if decorator.args:
                                view_info["permissions"] = self._extract_permission_classes(
                                    decorator.args[0]
                                )

                if view_info["methods"]:
                    views.append(view_info)

        return views

    def _extract_relationships(self, models: List[Dict[str, Any]]) -> Dict[str, List]:
        """
        Extract ForeignKey and ManyToMany relationships from models.
        """
        relationships = {"foreign_keys": [], "many_to_many": []}

        for model in models:
            for field in model["fields"]:
                field_type = field.get("type", "")

                if "ForeignKey" in field_type or "OneToOneField" in field_type:
                    relationships["foreign_keys"].append(
                        {
                            "model": model["name"],
                            "field": field["name"],
                            "related_model": self._extract_related_model(field_type),
                            "required": field.get("required", False),
                        }
                    )
                elif "ManyToManyField" in field_type:
                    relationships["many_to_many"].append(
                        {
                            "model": model["name"],
                            "field": field["name"],
                            "related_model": self._extract_related_model(field_type),
                        }
                    )

        return relationships

    def _extract_auth_requirements(self, views: List[Dict[str, Any]]) -> List[str]:
        """
        Extract authentication requirements from views.
        """
        auth_requirements = []

        for view in views:
            for perm in view.get("permissions", []):
                if any(auth in perm for auth in ["IsAuthenticated", "IsAdminUser"]):
                    auth_requirements.append(
                        f"{view['name']} requires {perm}"
                    )

        return list(set(auth_requirements))

    def _get_field_type(self, assign_node: ast.Assign) -> str:
        """Extract field type from assignment."""
        if isinstance(assign_node.value, ast.Call):
            func = assign_node.value.func
            if isinstance(func, ast.Name):
                return func.id
            elif isinstance(func, ast.Attribute):
                return func.attr
        return "Field"

    def _is_field_required(self, assign_node: ast.Assign) -> bool:
        """Check if a field is required."""
        if isinstance(assign_node.value, ast.Call):
            for keyword in assign_node.value.keywords:
                if keyword.arg == "blank":
                    value = ast.unparse(keyword.value)
                    if value == "False":
                        return True
                if keyword.arg == "null":
                    value = ast.unparse(keyword.value)
                    if value == "False":
                        return True
        return False

    def _get_field_default(self, assign_node: ast.Assign) -> str | None:
        """Extract default value for a field."""
        if isinstance(assign_node.value, ast.Call):
            for keyword in assign_node.value.keywords:
                if keyword.arg == "default":
                    return ast.unparse(keyword.value)
        return None

    def _get_field_choices(self, assign_node: ast.Assign) -> List[str] | None:
        """Extract choices for a field."""
        if isinstance(assign_node.value, ast.Call):
            for keyword in assign_node.value.keywords:
                if keyword.arg == "choices":
                    value_str = ast.unparse(keyword.value)
                    # Try to parse choices like STATUS_CHOICES = [('active', 'Active'), ...]
                    if "[" in value_str and "]" in value_str:
                        try:
                            # Extract choice values from tuples
                            choices = re.findall(r"['\"]([^'\"]+)['\"]", value_str)
                            # Return every other value (the actual choice values)
                            return choices[::2]
                        except Exception:
                            pass
        return None

    def _is_read_only_field(self, assign_node: ast.Assign) -> bool:
        """Check if a serializer field is read_only."""
        if isinstance(assign_node.value, ast.Call):
            for keyword in assign_node.value.keywords:
                if keyword.arg == "read_only":
                    value = ast.unparse(keyword.value)
                    if value == "True":
                        return True
        return False

    def _extract_permission_classes(self, value: ast.AST) -> List[str]:
        """Extract permission classes from AST node."""
        permissions = []
        value_str = ast.unparse(value)

        # Handle list like [IsAuthenticated, IsAdminUser]
        if "[" in value_str and "]" in value_str:
            try:
                # Extract class names
                perms = re.findall(r"(\w+)(?=\s*[,\]])", value_str)
                return [p for p in perms if p and not p.startswith("[")]
            except Exception:
                pass

        return permissions

    def _extract_related_model(self, field_type: str) -> str:
        """Extract related model name from ForeignKey(RelatedModel, ...)."""
        # Remove parentheses and split
        clean = re.sub(r"\(.*?\)", "", field_type)
        return clean.replace("Field", "").replace("ForeignKey", "").replace("OneToOne", "")

    def _generate_ai_prompt(
        self,
        app_name: str,
        analysis: Dict[str, Any],
        source_code: Dict[str, str]
    ) -> str:
        """
        Use AI to generate a comprehensive prompt for test generation.

        This method:
        1. Analyzes the structured data
        2. Uses AI to create a detailed prompt that includes all necessary information
        3. Returns the AI-generated prompt string
        """
        console.print(f"    [dim]→ Generating AI prompt for {app_name}...[/dim]")

        # Build the analysis context for AI
        analysis_context = self._build_analysis_context(app_name, analysis)

        # Use AI to generate the detailed test generation prompt
        system_prompt = """You are an expert Django and DRF test architect. Analyze the provided Django app structure and generate a comprehensive, detailed prompt that will be used to generate complete test cases.

Your task:
1. Analyze the models, serializers, views, and endpoints
2. Understand the relationships between models (FK, M2M)
3. Identify required fields, optional fields, and validation rules
4. Determine authentication and permission requirements
5. Generate a detailed prompt that includes ALL necessary information for test generation

Return ONLY the prompt text - no markdown, no explanation."""

        user_prompt = f"""Generate a comprehensive test generation prompt for this Django app:

## App Analysis Context:
{analysis_context}

## Source Code Sections:
"""

        # Add source code sections
        for key, content in source_code.items():
            user_prompt += f"\n### {key.upper()}\n```python\n{content[:3000]}\n```\n"

        # Add authentication response structure information if detected
        if "auth_response_structure" in analysis:
            auth_struct = analysis["auth_response_structure"]
            if auth_struct and auth_struct.get("detected"):
                token_path = auth_struct.get('token_path', 'access')
                login_url = auth_struct.get('login_url', '/api/user/login/')
                response_format = auth_struct.get('response_format', 'flat')
                auth_method = auth_struct.get('auth_method', 'none')

                # Handle different authentication methods
                if auth_method == "cookie_jwt":
                    cookie_names = auth_struct.get('cookie_names', ['access_token'])
                    main_cookie = cookie_names[0] if cookie_names else 'access_token'
                    data_key = auth_struct.get('data_key', 'data')
                    message_key = auth_struct.get('message_key', 'message')

                    user_prompt += f"""
## CRITICAL: DETECTED COOKIE-BASED JWT AUTHENTICATION
- The app uses COOKIE-BASED JWT authentication (NOT Bearer tokens)
- Login URL: {login_url}
- Cookie names: {', '.join(cookie_names)}
- Response format: NESTED (data in 'data' key)
- Data key: '{data_key}'
- Message key: '{message_key}'
- Token key: '{token_path}'

## CRITICAL AUTHENTICATION HELPER INSTRUCTIONS:
The authentication helper method MUST use COOKIE-BASED authentication:

```python
def authenticate_jwt(self, email, password):
    \"\"\"
    Helper method to authenticate user and set JWT cookies.
    Uses cookie-based authentication as detected from the actual code.
    \"\"\"
    payload = {{'email': email, 'password': password}}
    response = self.client.post(
        '{login_url}',
        data=json.dumps(payload),
        content_type='application/json'
    )
    if response.status_code == 200:
        data = response.json()
        # Handle NESTED response structure
        if isinstance(data, dict) and "data" in data:
            user_data = data["data"]
            access_token = user_data.get("{token_path}")
        else:
            access_token = data.get("{token_path}")

        if access_token:
            # Set cookie for subsequent requests
            self.client.cookies['{main_cookie}'] = access_token
            return data
    return None
```

IMPORTANT: Do NOT use Bearer tokens or Authorization headers. Use cookies as shown above.

## CRITICAL: RESPONSE STRUCTURE HANDLING
The app uses NESTED response structures. Test assertions must access data correctly:

```python
# Login response structure
response = self.client.post('/api/user/login/', data=payload, content_type='application/json')
data = response.json()  # {{"message": "...", "data": {{"user": {{...}}, "access": "...", "refresh": "..."}}}}

# Access user data
user_data = data['data']['user']  # NOT data['user']

# Access tokens
access_token = data['data']['access']  # NOT data['access']
refresh_token = data['data']['refresh']  # NOT data['refresh']

# Profile response structure
response = self.client.get('/api/user/me/')
data = response.json()  # {{"message": "...", "data": {{"email": "...", "full_name": "...", ...}}}}
user_data = data['data']  # NOT the whole response
email = user_data['email']  # NOT data['email']
```

**ALL test assertions must use data['field'] or data['data']['field'] depending on the response structure.**
"""
                else:
                    user_prompt += f"""
## CRITICAL: DETECTED AUTHENTICATION RESPONSE STRUCTURE
- The actual login response has been ANALYZED and the token location is KNOWN
- Login URL: {login_url}
- Access Token Path: response.json()['{token_path}']
- Response Format: {response_format.upper()}

## CRITICAL AUTHENTICATION HELPER INSTRUCTIONS:
The authentication helper method MUST use the EXACT token path detected above:

```python
def authenticate_jwt(self, email, password):
    payload = {{'email': email, 'password': password}}
    response = self.client.post('{login_url}', data=json.dumps(payload), content_type='application/json')
    if response.status_code == 200:
        token = response.json()['{token_path}']  # CRITICAL: Use detected path, not 'access'
        self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'
        return response.json()
    return None
```

IMPORTANT: Do NOT assume the token is at response.json()['access']. Use the detected path: response.json()['{token_path}'
"""

        # Add URL parameters information if detected
        if "url_parameters" in analysis and analysis["url_parameters"]:
            url_params = analysis["url_parameters"]
            if url_params:
                user_prompt += """
## CRITICAL: URL PARAMETERS DETECTED
Some views require URL parameters beyond the base URL. These MUST be included in test URLs:

```python
# Example: UserRetrieveView requires user_id parameter
url = f'/api/user/details/{{str(user_id)}}/'
response = self.client.get(url)
```

Views with URL parameters:
"""
                for view_name, params in url_params.items():
                    param_info = ", ".join([f"{p['name']}: {p['type']}" for p in params])
                    user_prompt += f"- {view_name}: [{param_info}]\n"

        # Add permission analysis information if detected
        if "permission_analysis" in analysis and analysis["permission_analysis"]:
            perm_analysis = analysis["permission_analysis"]
            if perm_analysis:
                user_prompt += """
## CRITICAL: PERMISSION CLASS ANALYSIS
The app uses custom permission classes with specific logic. Test setup must account for these:

"""
                for perm_name, perm_info in perm_analysis.items():
                    user_prompt += f"**{perm_name}** (from {perm_info['module']}):\n"
                    if perm_info.get("checks_superuser"):
                        user_prompt += "- Checks for superuser status\n"
                    if perm_info.get("checks_roles"):
                        user_prompt += f"- Checks for roles: {', '.join(perm_info['checks_roles'])}\n"
                    if perm_info.get("checks_pages"):
                        user_prompt += "- Checks for page access (may require page assignments in tests)\n"
                    if perm_info.get("checks_authentication"):
                        user_prompt += "- Requires authentication\n"
                    user_prompt += "\n"

                user_prompt += """
**Important Test Setup Implications:**
- Superuser users bypass most permission checks
- Admin role may bypass page access restrictions
- Editor role may have restricted HTTP methods
- Viewer role likely only allows GET requests
- Users may need page assignments for certain endpoints
"""

        # Add Django-specific test generation instructions
        if "django_project" in analysis:
            django_info = analysis["django_project"]
            user_prompt += f"""
## DJANGO-SPECIFIC TEST GENERATION GUIDELINES

The project uses Django {django_info['django_version']} with DRF.

**Database Configuration:**
- Default engine: {django_info['database_config']['default_engine']}
- Test engine: {django_info['database_config']['test_engine']}

**User Model:**
- Custom user model: {django_info['authentication_settings']['user_model']}
- Use get_user_model() instead of importing User directly

**Authentication Configuration:**
- Uses JWT: {django_info['authentication_settings']['use_jwt']}
- Uses session: {django_info['authentication_settings']['use_session']}
- Login URL: {django_info['authentication_settings']['login_url']}

**Middleware:**
- {len(django_info['middleware'])} middleware classes configured

**Test Database Setup:**
- Use Django's TestCase which handles database setup
- Use create_user() method for creating users
- Handle UUID primary keys properly (use str() when needed)
- Use --keepdb flag for performance
"""

        # Add DRF-specific guidance if applicable
        if "drf_views" in analysis and analysis["drf_views"]:
            drf_views = analysis["drf_views"]
            if drf_views.get("viewsets"):
                user_prompt += """
**ViewSet Testing Guidelines:**
- ViewSets automatically provide list, create, retrieve, update, destroy endpoints
- Test each standard action separately
- URL patterns typically: /api/model/ (list/create), /api/model/{{id}}/ (retrieve/update/destroy)
- Permission classes on ViewSets apply to all actions unless specified
"""
            if drf_views.get("api_views"):
                user_prompt += """
**APIView Testing Guidelines:**
- APIViews require explicit HTTP method definitions
- Test each defined method separately
- URL patterns are manually defined in urls.py
- Permission classes apply to the entire view unless per-method permissions
"""

        user_prompt += """
## Instructions for Prompt Generation:
Based on the above analysis, generate a detailed prompt that includes:

1. **Model Information:**
   - List all models with their field names and types
   - Identify required fields vs optional fields
   - List all foreign key relationships and what models need to be created first
   - List all many-to-many relationships and when they should be set

2. **Serializer Information:**
   - List all serializers and which models they serialize
   - Identify required fields for POST/PUT operations
   - Identify read-only fields that should not be included in test data
   - Note any special validation rules or constraints

3. **View Information:**
   - List all views with their HTTP methods (GET, POST, PUT, PATCH, DELETE)
   - Identify which views require authentication
   - Identify which views require specific permissions
   - Note any special view logic or permissions

4. **Endpoint Information:**
   - List all endpoints with their URLs and HTTP methods
   - Identify which endpoints require authentication
   - Identify what data should be sent to each endpoint
   - Identify what data should NOT be sent (read-only fields, auto-generated fields)

5. **Test Data Guidelines:**
   - What test data should be created for each model
   - What values are valid vs invalid for each field
   - How to handle relationships (create related objects first)
   - What edge cases to test (required fields missing, invalid data types, etc.)

6. **Authentication Setup:**
   - How to authenticate for protected endpoints
   - What user fields are needed for create_user()
   - How to handle foreign key fields in user creation

Return ONLY the prompt text - this will be used to generate actual test code. Be specific and detailed."""

        # Save what's being sent to AI to file (full prompt)
        ai_input_data = f"System Prompt:\n{system_prompt}\n\nUser Prompt (full):\n{user_prompt}\n\nFull prompt length: {len(user_prompt)} chars"
        ai_input_file = self._save_analysis_to_file(app_name, ai_input_data, "ai_input")
        console.print(f"    [dim]✓ AI input saved to:[/dim] {ai_input_file} ({len(user_prompt)} chars)")

        response = self.ai_helper.call_with_retry(
            model=self.ai_helper.MODEL,
            max_tokens=self.MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        if response:
            ai_generated_prompt = response.choices[0].message.content

            # Clean the response
            ai_generated_prompt = ai_generated_prompt.strip()
            if ai_generated_prompt.startswith("```"):
                ai_generated_prompt = ai_generated_prompt.split("```")[1].strip()
            if ai_generated_prompt.startswith("prompt"):
                ai_generated_prompt = ai_generated_prompt[6:].strip()

            # Save what AI returned to file
            ai_output_file = self._save_analysis_to_file(app_name, ai_generated_prompt, "ai_output")
            console.print(f"    [dim]✓ AI output saved to:[/dim] {ai_output_file}")

            console.print(f"    [green]✓ AI prompt generated ({len(ai_generated_prompt)} chars)[/green]")
            return ai_generated_prompt
        else:
            console.print(f"    [red]✗ Failed to generate AI prompt after retries[/red]")
            # Fallback to a basic prompt
            return self._fallback_prompt(app_name, analysis)

    def _build_analysis_context(self, app_name: str, analysis: Dict[str, Any]) -> str:
        """Build a readable analysis context string."""
        console.print(f"\n  [bold cyan]→ Building analysis context for {app_name}...[/bold cyan]")

        context = f"\n## App Name: {app_name}\n"

        # Models
        if analysis["models"]:
            context += "\n### Models:\n"
            for model in analysis["models"]:
                context += f"\n**{model['name']}**\n"
                for field in model["fields"]:
                    req = " (required)" if field.get("required") else " (optional)"
                    context += f"  - {field['name']}: {field['type']}{req}\n"

        # Serializers
        if analysis["serializers"]:
            context += "\n### Serializers:\n"
            for serializer in analysis["serializers"]:
                context += f"\n**{serializer['name']}**"
                if serializer.get("model"):
                    context += f" (Model: {serializer['model']})"
                context += "\n"
                for field in serializer["fields"]:
                    ro = " [READ-ONLY]" if field.get("read_only") else ""
                    req = " [REQUIRED]" if field.get("required") else ""
                    context += f"  - {field['name']}: {field['type']}{ro}{req}\n"

        # Views
        if analysis["views"]:
            context += "\n### Views:\n"
            for view in analysis["views"]:
                context += f"\n**{view['name']}** ({view['type']})\n"
                context += f"  Methods: {', '.join(view['methods'])}\n"
                if view["permissions"]:
                    context += f"  Permissions: {', '.join(view['permissions'])}\n"

        # Endpoints
        if analysis["endpoints"]:
            context += "\n### Endpoints:\n"
            for ep in analysis["endpoints"]:
                auth = " [AUTH]" if ep["requires_auth"] else " [PUBLIC]"
                context += f"  - {ep['methods']} {ep['url']}{auth}\n"

        # Relationships
        rels = analysis["relationships"]
        if rels["foreign_keys"]:
            context += "\n### Foreign Key Relationships:\n"
            for fk in rels["foreign_keys"]:
                req = " [required]" if fk.get("required") else ""
                context += f"  - {fk['model']}.{fk['field']} → {fk['related_model']}{req}\n"

        if rels["many_to_many"]:
            context += "\n### Many-to-Many Relationships:\n"
            for m2m in rels["many_to_many"]:
                context += f"  - {m2m['model']}.{m2m['field']} → {m2m['related_model']}\n"

        return context

    def _fallback_prompt(self, app_name: str, analysis: Dict[str, Any]) -> str:
        """Generate a basic fallback prompt if AI fails."""
        return f"""Generate Django test cases for the {app_name} app.

Models to test: {', '.join([m['name'] for m in analysis['models']])}
Endpoints to test: {len(analysis['endpoints'])}
Authentication required for: {len([e for e in analysis['endpoints'] if e['requires_auth']])} endpoints

Generate complete test cases with proper setup, authentication, and assertions."""

    # ENHANCED ANALYSIS METHODS

    def _detect_auth_method(self, source_code: Dict[str, str], app_dir: Path) -> Dict[str, Any]:
        """
        Detect the authentication method used by the app.
        
        Returns:
            Dict with authentication details including:
            - method: 'cookie_jwt', 'header_jwt', 'session', or 'none'
            - token_names: List of token names used
            - cookie_settings: Cookie configuration if cookie-based
            - login_url: Detected login endpoint
        """
        auth_info = {
            "method": "none",
            "token_names": [],
            "cookie_settings": {},
            "login_url": None,
            "detected": False,
            "evidence": []
        }

        # Analyze permission.py for cookie-based auth
        if "permissions" in source_code:
            perm_auth_info = self._analyze_permission_file_for_auth(source_code["permissions"])
            auth_info["evidence"].extend(perm_auth_info["evidence"])
            auth_info["token_names"].extend(perm_auth_info["token_names"])

        # Analyze core/permission.py for cookie-based auth
        core_perm_path = self.repo_path / "core" / "permission.py"
        if core_perm_path.exists():
            core_perm_content = core_perm_path.read_text()
            core_auth_info = self._analyze_core_permission_file(core_perm_content)
            auth_info["evidence"].extend(core_auth_info["evidence"])
            auth_info["token_names"].extend(core_auth_info["token_names"])
            auth_info["cookie_settings"].update(core_auth_info["cookie_settings"])

        # Analyze views for authentication patterns
        if "views" in source_code:
            views_auth_info = self._analyze_views_for_auth(source_code["views"])
            auth_info["evidence"].extend(views_auth_info["evidence"])
            auth_info["token_names"].extend(views_auth_info["token_names"])

        # Analyze urls.py for login endpoint
        if "urls" in source_code:
            login_info = self._detect_login_endpoint(source_code["urls"])
            if login_info["login_url"]:
                auth_info["login_url"] = login_info["login_url"]

        # Determine final authentication method
        if auth_info["evidence"]:
            auth_info["detected"] = True
            auth_info["evidence"] = list(set(auth_info["evidence"]))  # Remove duplicates
            auth_info["token_names"] = list(set(auth_info["token_names"]))  # Remove duplicates

            if "cookie_authentication" in auth_info["evidence"]:
                auth_info["method"] = "cookie_jwt"
            elif "jwt_authentication" in auth_info["evidence"]:
                auth_info["method"] = "header_jwt"
            elif "session_authentication" in auth_info["evidence"]:
                auth_info["method"] = "session"

        return auth_info

    def _analyze_permission_file_for_auth(self, perm_content: str) -> Dict[str, Any]:
        """Analyze permission.py for authentication patterns."""
        info = {"evidence": [], "token_names": []}

        # Look for cookie-based JWT patterns
        if "request.COOKIES.get" in perm_content:
            info["evidence"].append("cookie_authentication")
            cookie_names = re.findall(r'COOKIES\.get\(["\']([^"\']+)["\']', perm_content)
            info["token_names"].extend(cookie_names)

        # Look for JWT patterns
        if "JWTAuthentication" in perm_content:
            info["evidence"].append("jwt_authentication")

        # Look for refresh token patterns
        if "RefreshToken" in perm_content:
            info["evidence"].append("jwt_refresh_tokens")

        return info

    def _analyze_core_permission_file(self, core_perm_content: str) -> Dict[str, Any]:
        """Analyze core/permission.py for authentication patterns."""
        info = {"evidence": [], "token_names": [], "cookie_settings": {}}

        # Look for cookie token names
        cookie_names = re.findall(r'COOKIES\.get\(["\']([^"\']+)["\']', core_perm_content)
        if cookie_names:
            info["token_names"].extend(cookie_names)
            info["evidence"].append("cookie_authentication")

        # Look for cookie setting patterns
        if "httponly=True" in core_perm_content:
            info["cookie_settings"]["httponly"] = True
            info["evidence"].append("httponly_cookies")

        if "secure=True" in core_perm_content:
            info["cookie_settings"]["secure"] = True

        if 'samesite="None"' in core_perm_content or "samesite='None'" in core_perm_content:
            info["cookie_settings"]["samesite"] = "None"

        # Look for JWT patterns
        if "JWTAuthentication" in core_perm_content:
            info["evidence"].append("jwt_authentication")

        if "RefreshToken" in core_perm_content:
            info["evidence"].append("jwt_refresh_tokens")

        return info

    def _analyze_views_for_auth(self, views_content: str) -> Dict[str, Any]:
        """Analyze views.py for authentication patterns."""
        info = {"evidence": [], "token_names": []}

        # Look for cookie setting in responses
        if "set_cookie" in views_content:
            info["evidence"].append("cookie_setting_in_views")

        # Extract cookie names used in set_cookie calls
        cookie_names = re.findall(r'set_cookie\(\s*key=["\']([^"\']+)["\']', views_content)
        if cookie_names:
            info["token_names"].extend(cookie_names)

        return info

    def _detect_login_endpoint(self, urls_content: str) -> Dict[str, Any]:
        """Detect login endpoint from urls.py."""
        info = {"login_url": None}

        # Look for login URL patterns
        login_patterns = re.findall(
            r'path\([\'"]([^\'"]*login[^\'"]*)[\'"]', urls_content
        )
        if login_patterns:
            info["login_url"] = f"/{login_patterns[0].strip('/')}/"

        return info

    def _detect_response_structure(self, source_code: Dict[str, str]) -> Dict[str, Any]:
        """
        Detect the response structure patterns used in the views.

        Returns:
            Dict with:
            - structure_type: 'nested', 'flat', or 'mixed'
            - data_key: The key used for nested data (e.g., 'data', 'results')
            - message_key: The key used for messages (e.g., 'message', 'detail')
            - token_key: The key used for tokens (e.g., 'access', 'access_token')
        """
        structure_info = {
            "structure_type": "flat",
            "data_key": "data",
            "message_key": "message",
            "token_key": "access",
            "detected": False,
            "evidence": []
        }

        if "views" not in source_code:
            return structure_info

        views_content = source_code["views"]
        structure_info.update(self._parse_response_structure(views_content))

        return structure_info

    def _parse_response_structure(self, views_content: str) -> Dict[str, Any]:
        """Analyze view code to detect response structure patterns."""
        info = {
            "structure_type": "flat",
            "data_key": "data",
            "message_key": "message",
            "token_key": "access",
            "detected": False,
            "evidence": []
        }

        # Look for Response patterns
        response_patterns = re.findall(
            r'Response\(\s*\{([^}]+)\}', views_content, re.DOTALL
        )

        for pattern in response_patterns:
            # Check for nested data structure
            if '"data"' in pattern or "'data'" in pattern:
                info["structure_type"] = "nested"
                info["data_key"] = "data"
                info["evidence"].append("nested_data_structure")

            # Check for message key
            if '"message"' in pattern or "'message'" in pattern:
                info["message_key"] = "message"
                info["evidence"].append("message_key_present")

            # Check for token keys
            if '"access"' in pattern or "'access'" in pattern:
                info["token_key"] = "access"
                info["evidence"].append("access_token_key")

        if info["evidence"]:
            info["detected"] = True

        return info

    def _extract_url_parameters(self, source_code: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract URL parameters from view method signatures.

        Returns:
            Dict mapping view names to their URL parameters:
            {
                "UserRetrieveView": [{"name": "user_id", "type": "str"}],
                ...
            }
        """
        url_params = {}

        if "views" not in source_code:
            return url_params

        try:
            tree = ast.parse(source_code["views"])
        except Exception as e:
            console.print(f"  [red]Error parsing views.py: {e}[/red]")
            return url_params

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                view_name = node.name
                params = self._extract_class_method_params(node)
                if params:
                    url_params[view_name] = params

        return url_params

    def _extract_class_method_params(self, class_node: ast.ClassDef) -> List[Dict[str, str]]:
        """Extract URL parameters from class-based view methods."""
        params = []

        # Common HTTP methods that might have URL parameters
        http_methods = ["get", "post", "put", "patch", "delete"]

        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name.lower() in http_methods:
                # Skip self and request parameters, look for URL params
                url_params = []
                for arg in item.args.args:
                    if arg.arg not in ["self", "request"]:
                        param_type = self._get_param_type_from_annotation(arg)
                        url_params.append({
                            "name": arg.arg,
                            "type": param_type
                        })
                params.extend(url_params)

        return params

    def _get_param_type_from_annotation(self, arg: ast.arg) -> str:
        """Get the type annotation from a function argument."""
        if arg.annotation:
            return ast.unparse(arg.annotation)
        return "str"

    def _analyze_permission_classes(self, source_code: Dict[str, str], app_dir: Path) -> Dict[str, Dict[str, Any]]:
        """
        Analyze permission classes to understand access control.

        Returns:
            Dict mapping permission class names to their analysis:
            {
                "HasPageAccess": {
                    "type": "custom",
                    "checks_superuser": True,
                    "checks_roles": ["admin", "editor", "viewer"],
                    "checks_pages": True,
                    "logic": "..."
                },
                ...
            }
        """
        permissions = {}

        # Check if permission.py exists in app
        if "permissions" in source_code:
            perm_content = source_code["permissions"]
            app_perms = self._analyze_permission_classes_in_file(perm_content, "app")
            permissions.update(app_perms)

        # Check core/permission.py
        core_perm_path = self.repo_path / "core" / "permission.py"
        if core_perm_path.exists():
            core_perm_content = core_perm_path.read_text()
            core_perms = self._analyze_permission_classes_in_file(core_perm_content, "core")
            permissions.update(core_perms)

        return permissions

    def _analyze_permission_classes_in_file(self, content: str, module: str) -> Dict[str, Any]:
        """Analyze permission classes in a file."""
        permissions = {}

        try:
            tree = ast.parse(content)
        except Exception:
            return permissions

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Permission" in node.name:
                perm_name = node.name
                perm_info = {
                    "module": module,
                    "type": "custom",
                    "checks_superuser": False,
                    "checks_roles": [],
                    "checks_pages": False,
                    "checks_authentication": False,
                    "logic": content[:500]  # First 500 chars of the class
                }

                # Analyze has_permission method
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "has_permission":
                        method_code = ast.unparse(item)
                        perm_info["logic"] = method_code

                        # Check what the permission examines
                        if "is_superuser" in method_code:
                            perm_info["checks_superuser"] = True

                        if "is_authenticated" in method_code or "request.user" in method_code:
                            perm_info["checks_authentication"] = True

                        # Look for role checks
                        role_patterns = re.findall(
                            r'role\.name\s*==\s*["\']([^"\']+)["\']',
                            method_code
                        )
                        perm_info["checks_roles"] = role_patterns

                        # Look for page checks
                        if "pages" in method_code.lower() or "page" in method_code.lower():
                            perm_info["checks_pages"] = True

                permissions[perm_name] = perm_info

        return permissions

    def _build_auth_response_structure(self, auth_info: Dict[str, Any], response_structure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build auth_response_structure for compatibility with existing code.

        This maps the enhanced analysis to the original format expected by test generation.
        """
        if auth_info.get("method") == "cookie_jwt":
            return {
                "login_url": auth_info.get("login_url", "/api/user/login/"),
                "token_path": response_structure.get("token_key", "access"),
                "response_format": response_structure.get("structure_type", "nested"),
                "detected": True,
                "error": None,
                "auth_method": "cookie_jwt",
                "cookie_names": auth_info.get("token_names", ["access_token"]),
                "cookie_settings": auth_info.get("cookie_settings", {}),
                "data_key": response_structure.get("data_key", "data"),
                "message_key": response_structure.get("message_key", "message")
            }
        else:
            return {
                "login_url": auth_info.get("login_url", "/api/user/login/"),
                "token_path": response_structure.get("token_key", "access"),
                "response_format": response_structure.get("structure_type", "flat"),
                "detected": True,
                "error": None,
                "auth_method": auth_info.get("method", "none")
            }
