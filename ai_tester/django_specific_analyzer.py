"""
Django-Specific Analysis Enhancements for Test Generation

This module provides Django-specific analysis capabilities that work across
all Django projects, focusing on common Django and DRF patterns.
"""

import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from rich.console import Console

console = Console()


class DjangoSpecificAnalyzer:
    """
    Django-specific analyzer that understands Django/DRF patterns
    across different project configurations.
    """

    def __init__(self, repo_path: str, source_code: Dict[str, str]):
        self.repo_path = Path(repo_path)
        self.source_code = source_code
        self.settings_path = self._find_django_settings()

    def _find_django_settings(self) -> Optional[Path]:
        """Find Django settings file across different project structures."""
        possible_settings = [
            self.repo_path / "settings.py",
            self.repo_path / "config" / "settings.py",
            self.repo_path / "usea" / "settings.py",  # Common pattern
            self.repo_path / "myproject" / "settings.py",  # Common pattern
        ]

        for settings_file in possible_settings:
            if settings_file.exists():
                return settings_file

        # Try to find settings.py in any subdirectory
        for settings_file in self.repo_path.rglob("settings.py"):
            if not self._should_skip(settings_file):
                return settings_file

        return None

    def _should_skip(self, path: Path) -> bool:
        """Check if a path should be skipped."""
        skip_dirs = {"venv", "env", "site-packages", "__pycache__",
                    ".git", "node_modules", ".probe_venv"}
        return any(skip_dir in path.parts for skip_dir in skip_dirs)

    def analyze_django_project(self) -> Dict[str, Any]:
        """
        Comprehensive Django project analysis.

        Returns detailed information about:
        - Django version
        - REST framework configuration
        - Authentication settings
        - Installed apps
        - Middleware configuration
        - Custom authentication backends
        - Custom user model
        """
        analysis = {
            "django_version": self._detect_django_version(),
            "rest_framework_config": self._analyze_rest_framework_config(),
            "authentication_settings": self._analyze_authentication_settings(),
            "installed_apps": self._get_installed_apps(),
            "middleware": self._get_middleware(),
            "custom_user_model": self._detect_custom_user_model(),
            "url_configuration": self._analyze_url_configuration(),
            "database_config": self._analyze_database_config(),
        }

        return analysis

    def _detect_django_version(self) -> str:
        """Detect Django version from requirements or environment."""
        # Check requirements.txt
        requirements_files = [
            self.repo_path / "requirements.txt",
            self.repo_path / "requirements" / "base.txt",
            self.repo_path / "requirements" / "local.txt",
        ]

        for req_file in requirements_files:
            if req_file.exists():
                content = req_file.read_text()
                django_match = re.search(r'django==([0-9.]+(?:\.[0-9.]+)*)', content)
                if django_match:
                    return django_match.group(1)

        # Try to import Django and get version
        try:
            import django
            return django.get_version()
        except ImportError:
            return "unknown"

    def _analyze_rest_framework_config(self) -> Dict[str, Any]:
        """Analyze Django REST Framework configuration."""
        config = {
            "installed": False,
            "authentication_classes": [],
            "permission_classes": [],
            "pagination": None,
            "default_renderer_classes": [],
        }

        if not self.settings_path:
            return config

        try:
            settings_content = self.settings_path.read_text()

            # Check if DRF is installed
            if "'rest_framework'" in settings_content or '"rest_framework"' in settings_content:
                config["installed"] = True

            # Extract REST_AUTHENTICATION_CLASSES
            auth_classes = re.findall(
                r'REST_FRAMEWORK\s*=\s*\{[^}]*["\']?AUTHENTICATION_CLASSES["\']?\s*:\s*\[(.*?)\]',
                settings_content,
                re.DOTALL
            )
            if auth_classes:
                config["authentication_classes"] = [cls.strip().strip('\'"')
                                                  for cls in auth_classes[0].split(',')]

            # Extract REST_FRAMEWORK permission classes
            perm_classes = re.findall(
                r'REST_FRAMEWORK\s*=\s*\{[^}]*["\']?DEFAULT_PERMISSION_CLASSES["\']?\s*:\s*\[(.*?)\]',
                settings_content,
                re.DOTALL
            )
            if perm_classes:
                config["permission_classes"] = [cls.strip().strip('\'"')
                                                  for cls in perm_classes[0].split(',')]

            # Extract pagination settings
            pagination = re.findall(
                r'REST_FRAMEWORK\s*=\s*\{[^}]*["\']?DEFAULT_PAGINATION_CLASS["\']?\s*:\s*["\']([^"\']+)["\']',
                settings_content
            )
            if pagination:
                config["pagination"] = pagination[0]

        except Exception as e:
            console.print(f"  [yellow]Error analyzing DRF config: {e}[/yellow]")

        return config

    def _analyze_authentication_settings(self) -> Dict[str, Any]:
        """Analyze Django authentication settings."""
        settings = {
            "auth_backends": [],
            "user_model": "auth.User",  # Default
            "login_url": "/accounts/login/",
            "use_jwt": False,
            "use_session": True,
        }

        if not self.settings_path:
            return settings

        try:
            settings_content = self.settings_path.read_text()

            # Extract AUTHENTICATION_BACKENDS
            auth_backends = re.findall(
                r'AUTHENTICATION_BACKENDS\s*=\s*\[(.*?)\]',
                settings_content,
                re.DOTALL
            )
            if auth_backends:
                backends = [b.strip().strip('\'"')
                            for b in auth_backends[0].split(',')]
                settings["auth_backends"] = backends

                # Detect JWT authentication
                for backend in backends:
                    if 'jwt' in backend.lower() or 'token' in backend.lower():
                        settings["use_jwt"] = True
                        settings["use_session"] = False
                        break

            # Extract AUTH_USER_MODEL
            user_model = re.search(
                r'AUTH_USER_MODEL\s*=\s*["\']([^"\']+)["\']',
                settings_content
            )
            if user_model:
                settings["user_model"] = user_model.group(1)

            # Extract LOGIN_URL
            login_url = re.search(
                r'LOGIN_URL\s*=\s*["\']([^"\']+)["\']',
                settings_content
            )
            if login_url:
                settings["login_url"] = login_url.group(1)

        except Exception as e:
            console.print(f"  [yellow]Error analyzing auth settings: {e}[/yellow]")

        return settings

    def _get_installed_apps(self) -> List[str]:
        """Get list of installed Django apps."""
        apps = []

        if not self.settings_path:
            return apps

        try:
            settings_content = self.settings_path.read_text()

            # Extract INSTALLED_APPS
            installed_apps = re.findall(
                r'INSTALLED_APPS\s*=\s*\[(.*?)\]',
                settings_content,
                re.DOTALL
            )
            if installed_apps:
                apps = [app.strip().strip('\'"')
                        for app in installed_apps[0].split(',')
                        if app.strip() and not app.strip().startswith('#')]

        except Exception as e:
            console.print(f"  [yellow]Error getting installed apps: {e}[/yellow]")

        return apps

    def _get_middleware(self) -> List[str]:
        """Get list of Django middleware."""
        middleware = []

        if not self.settings_path:
            return middleware

        try:
            settings_content = self.settings_path.read_text()

            # Extract MIDDLEWARE
            middleware_list = re.findall(
                r'MIDDLEWARE\s*=\s*\[(.*?)\]',
                settings_content,
                re.DOTALL
            )
            if middleware_list:
                middleware = [mw.strip().strip('\'"')
                           for mw in middleware_list[0].split(',')
                           if mw.strip() and not mw.strip().startswith('#')]

        except Exception as e:
            console.print(f"  [yellow]Error getting middleware: {e}[/yellow]")

        return middleware

    def _detect_custom_user_model(self) -> Optional[str]:
        """Detect custom user model."""
        # Check settings
        if self.settings_path:
            settings_content = self.settings_path.read_text()
            user_model_match = re.search(
                r'AUTH_USER_MODEL\s*=\s*["\']([^"\']+)["\']',
                settings_content
            )
            if user_model_match:
                return user_model_match.group(1)

        # Check common user models
        common_user_models = [
            "apps.user.models.User",
            "user.models.User",
            "accounts.models.User",
        ]

        for app in self._get_installed_apps():
            if 'user' in app.lower():
                # Try to find the User model
                app_path = self.repo_path / app.replace('.', '/')
                models_path = app_path / "models.py"
                if models_path.exists():
                    content = models_path.read_text()
                    if "class User" in content and "AbstractBaseUser" in content:
                        return f"{app}.models.User"

        return None

    def _analyze_url_configuration(self) -> Dict[str, Any]:
        """Analyze Django URL configuration."""
        config = {
            "root_urlconf": None,
            "base_url": "",
            "include_patterns": [],
            "api_prefixes": [],
        }

        if not self.settings_path:
            return config

        try:
            settings_content = self.settings_path.read_text()

            # Extract ROOT_URLCONF
            root_urlconf = re.search(
                r'ROOT_URLCONF\s*=\s*["\']([^"\']+)["\']',
                settings_content
            )
            if root_urlconf:
                config["root_urlconf"] = root_urlconf.group(1)

        except Exception as e:
            console.print(f"  [yellow]Error analyzing URL config: {e}[/yellow]")

        return config

    def _analyze_database_config(self) -> Dict[str, Any]:
        """Analyze database configuration."""
        config = {
            "default_engine": "unknown",
            "test_engine": "unknown",
        }

        if not self.settings_path:
            return config

        try:
            settings_content = self.settings_path.read_text()

            # Extract DATABASES
            databases_match = re.search(
                r'DATABASES\s*=\s*\{(.*?)\}',
                settings_content,
                re.DOTALL
            )
            if databases_match:
                db_config = databases_match.group(1)
                # Extract default engine
                default_engine = re.search(
                    r'"?"?"?default["?\s]*:\s*\{[^}]*["\']?ENGINE["\']?\s*:\s*["\']([^"\']+)["\']',
                    db_config
                )
                if default_engine:
                    config["default_engine"] = default_engine.group(1)

                # Extract test database engine
                test_engine = re.search(
                    r'TEST["?\s]*:\s*\{[^}]*["\']?ENGINE["\']?\s*:\s*["\']([^"\']+)["\']',
                    db_config
                )
                if test_engine:
                    config["test_engine"] = test_engine.group(1)

        except Exception as e:
            console.print(f"  [yellow]Error analyzing database config: {e}[/yellow]")

        return config

    def analyze_drf_views(self) -> Dict[str, Any]:
        """
        Analyze Django REST Framework views for common patterns.

        Detects:
        - ViewSet classes
        - Generic views
        - APIView classes
        - Function-based API views
        - View inheritance patterns
        """
        drf_analysis = {
            "viewsets": [],
            "generic_views": [],
            "api_views": [],
            "function_based_views": [],
            "authentication_mixins": [],
            "permission_classes": {},
        }

        if "views" not in self.source_code:
            return drf_analysis

        try:
            tree = ast.parse(self.source_code["views"])

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Detect ViewSet classes
                    if self._is_drf_viewset(node):
                        viewset_info = self._analyze_viewset(node)
                        drf_analysis["viewsets"].append(viewset_info)

                    # Detect Generic views
                    elif self._is_drf_generic_view(node):
                        generic_info = self._analyze_generic_view(node)
                        drf_analysis["generic_views"].append(generic_info)

                    # Detect APIView classes
                    elif self._is_api_view(node):
                        api_view_info = self._analyze_api_view(node)
                        drf_analysis["api_views"].append(api_view_info)

                        # Extract permission classes
                        perms = self._extract_view_permissions(node)
                        if perms:
                            drf_analysis["permission_classes"][node.name] = perms

        except Exception as e:
            console.print(f"  [yellow]Error analyzing DRF views: {e}[/yellow]")

        return drf_analysis

    def _is_drf_viewset(self, node: ast.ClassDef) -> bool:
        """Check if a class is a DRF ViewSet."""
        base_classes = self._get_base_classes(node)
        drf_viewset_bases = [
            "ViewSet",
            "ModelViewSet",
            "ReadOnlyModelViewSet",
            "GenericViewSet"
        ]
        return any(base in drf_viewset_bases for base in base_classes)

    def _is_drf_generic_view(self, node: ast.ClassDef) -> bool:
        """Check if a class is a DRF generic view."""
        base_classes = self._get_base_classes(node)
        drf_generic_bases = [
            "ListAPIView",
            "CreateAPIView",
            "RetrieveAPIView",
            "UpdateAPIView",
            "DestroyAPIView",
            "ListCreateAPIView",
            "RetrieveUpdateAPIView",
            "RetrieveDestroyAPIView",
            "RetrieveUpdateDestroyAPIView"
        ]
        return any(base in drf_generic_bases for base in base_classes)

    def _is_api_view(self, node: ast.ClassDef) -> bool:
        """Check if a class is an APIView."""
        base_classes = self._get_base_classes(node)
        return "APIView" in base_classes

    def _get_base_classes(self, node: ast.ClassDef) -> List[str]:
        """Extract base class names from a class definition."""
        base_classes = []
        for base in node.bases:
            base_classes.append(ast.unparse(base))
        return base_classes

    def _analyze_viewset(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Analyze a DRF ViewSet."""
        info = {
            "name": node.name,
            "base_classes": self._get_base_classes(node),
            "methods": self._extract_viewset_methods(node),
            "permissions": self._extract_view_permissions(node),
        }
        return info

    def _analyze_generic_view(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Analyze a DRF generic view."""
        info = {
            "name": node.name,
            "base_classes": self._get_base_classes(node),
            "http_method": self._infer_http_method(node.name),
            "permissions": self._extract_view_permissions(node),
        }
        return info

    def _analyze_api_view(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Analyze an APIView."""
        info = {
            "name": node.name,
            "base_classes": self._get_base_classes(node),
            "methods": self._extract_api_view_methods(node),
            "permissions": self._extract_view_permissions(node),
        }
        return info

    def _extract_viewset_methods(self, node: ast.ClassDef) -> List[str]:
        """Extract standard ViewSet methods."""
        methods = []
        standard_methods = ["list", "create", "retrieve", "update",
                         "partial_update", "destroy"]

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name in standard_methods:
                methods.append(item.name)

        return methods

    def _extract_api_view_methods(self, node: ast.ClassDef) -> List[str]:
        """Extract HTTP methods from an APIView."""
        methods = []
        http_methods = ["get", "post", "put", "patch", "delete", "head", "options"]

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name.lower() in http_methods:
                methods.append(item.name.lower())

        return methods

    def _infer_http_method(self, class_name: str) -> str:
        """Infer HTTP method from generic view class name."""
        method_mapping = {
            "List": "GET",
            "Create": "POST",
            "Retrieve": "GET",
            "Update": "PUT",
            "Destroy": "DELETE",
            "RetrieveUpdate": ["GET", "PUT"],
            "RetrieveDestroy": ["GET", "DELETE"],
            "RetrieveUpdateDestroy": ["GET", "PUT", "DELETE"],
        }

        for pattern, method in method_mapping.items():
            if pattern in class_name:
                return method

        return "GET"

    def _extract_view_permissions(self, node: ast.ClassDef) -> List[str]:
        """Extract permission classes from a view."""
        permissions = []

        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "permission_classes":
                        # Extract from list [Permission1, Permission2]
                        if isinstance(item.value, ast.List):
                            permissions = [ast.unparse(elt).strip()
                                          for elt in item.value.elts]

        return permissions

    def generate_django_test_helpers(self, analysis: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate Django-specific test helper methods.

        Returns a dictionary of helper method names to their code.
        """
        helpers = {}

        # Authentication helper based on detected auth method
        auth_method = analysis.get("authentication_settings", {}).get("use_jwt", False)
        if auth_method:
            helpers["authenticate_jwt"] = self._generate_jwt_auth_helper(analysis)
        else:
            helpers["authenticate_session"] = self._generate_session_auth_helper(analysis)

        # Database helper
        helpers["setup_test_database"] = self._generate_db_helper(analysis)

        # Model helper
        helpers["create_test_models"] = self._generate_model_helper(analysis)

        return helpers

    def _generate_jwt_auth_helper(self, analysis: Dict[str, Any]) -> str:
        """Generate JWT authentication helper."""
        login_url = analysis.get("authentication_settings", {}).get("login_url", "/login/")

        # Check if cookie-based or header-based
        response_structure = analysis.get("response_structure", {})
        if response_structure.get("structure_type") == "nested":
            cookie_names = response_structure.get("cookie_names", ["access_token"])
            main_cookie = cookie_names[0] if cookie_names else "access_token"

            return f'''    def authenticate_jwt(self, email, password):
        """
        Helper method to authenticate user using cookie-based JWT authentication.
        Handles nested response structures: {{'data': {{...}}, 'message': '...'}}
        """
        payload = {{'email': email, 'password': password}}
        response = self.client.post(
            '{login_url}',
            data=json.dumps(payload),
            content_type='application/json'
        )
        if response.status_code == 200:
            data = response.json()
            # Handle nested response structure
            user_data = data.get('data', data)
            access_token = user_data.get('access')
            if access_token:
                # Set cookie for subsequent requests
                self.client.cookies['{main_cookie}'] = access_token
                return data
        return None'''
        else:
            # Header-based JWT
            return f'''    def authenticate_jwt(self, email, password):
        """
        Helper method to authenticate user using header-based JWT authentication.
        """
        payload = {{'email': email, 'password': password}}
        response = self.client.post(
            '{login_url}',
            data=json.dumps(payload),
            content_type='application/json'
        )
        if response.status_code == 200:
            token = response.json().get('access')
            if token:
                self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'
                return response.json()
        return None'''

    def _generate_session_auth_helper(self, analysis: Dict[str, Any]) -> str:
        """Generate session authentication helper."""
        login_url = analysis.get("authentication_settings", {}).get("login_url", "/login/")

        return f'''    def authenticate_session(self, email, password):
        """
        Helper method to authenticate user using Django session authentication.
        """
        response = self.client.post(
            '{login_url}',
            {{'email': email, 'password': password}}
        )
        return response.json() if response.status_code == 200 else None'''

    def _generate_db_helper(self, analysis: Dict[str, Any]) -> str:
        """Generate database helper for tests."""
        return '''    def setup_test_database(self):
        """
        Setup test database with common test data.
        """
        # Create common test data
        # This method should be customized based on your app's requirements
        pass'''

    def _generate_model_helper(self, analysis: Dict[str, Any]) -> str:
        """Generate model creation helper."""
        user_model = analysis.get("authentication_settings", {}).get(
            "user_model", "django.contrib.auth.models.User"
        )

        return f'''    def create_test_user(self, email, password, **kwargs):
        """
        Helper method to create a test user.
        Uses the detected user model: {user_model}
        """
        User = get_user_model()
        return User.objects.create_user(
            email=email,
            password=password,
            **kwargs
        )'''


def integrate_django_specific_features(original_analyzer) -> None:
    """
    Integrate Django-specific analysis into the original AppAnalyzer.

    This extends the analyzer with Django/DRF-specific capabilities
    without modifying the original source files.
    """
    # Add Django-specific methods to the original analyzer
    original_analyzer.analyze_django_project = DjangoSpecificAnalyzer.analyze_django_project
    original_analyzer.analyze_drf_views = DjangoSpecificAnalyzer.analyze_drf_views
    original_analyzer.generate_django_test_helpers = DjangoSpecificAnalyzer.generate_django_test_helpers

    console.print("[green]✓ Django-specific analysis features integrated[/green]")