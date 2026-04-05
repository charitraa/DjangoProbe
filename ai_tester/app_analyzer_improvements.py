"""
Enhanced AppAnalyzer with improved authentication and response structure detection.

This module extends the existing AppAnalyzer to:
1. Detect cookie-based JWT authentication
2. Parse response structure patterns
3. Extract URL parameters from view signatures
4. Analyze permission class implementations
5. Generate appropriate test helpers
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from rich.console import Console

console = Console()


class EnhancedAppAnalyzer:
    """
    Enhanced analyzer that detects authentication methods and response patterns.
    """

    def __init__(self, repo_path: str, source_code: Dict[str, str]):
        self.repo_path = Path(repo_path)
        self.source_code = source_code

    def detect_authentication_method(self) -> Dict[str, Any]:
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
        if "permissions" in self.source_code:
            perm_auth_info = self._analyze_permission_file()
            auth_info.update(perm_auth_info)

        # Analyze core/permission.py for cookie-based auth
        core_perm_path = self.repo_path / "core" / "permission.py"
        if core_perm_path.exists():
            core_perm_content = core_perm_path.read_text()
            core_auth_info = self._analyze_core_permission_file(core_perm_content)
            auth_info.update(core_auth_info)

        # Analyze views for authentication patterns
        if "views" in self.source_code:
            views_auth_info = self._analyze_views_for_auth()
            auth_info.update(views_auth_info)

        # Analyze urls.py for login endpoint
        if "urls" in self.source_code:
            login_info = self._detect_login_endpoint()
            auth_info.update(login_info)

        # Determine final authentication method
        if auth_info.get("evidence"):
            auth_info["detected"] = True
            if "cookie" in [e.lower() for e in auth_info["evidence"]]:
                auth_info["method"] = "cookie_jwt"
            elif "jwt" in [e.lower() for e in auth_info["evidence"]]:
                auth_info["method"] = "header_jwt"
            elif "session" in [e.lower() for e in auth_info["evidence"]]:
                auth_info["method"] = "session"

        return auth_info

    def _analyze_permission_file(self) -> Dict[str, Any]:
        """Analyze app permission.py for authentication patterns."""
        info = {"evidence": [], "cookie_settings": {}}

        perm_content = self.source_code.get("permissions", "")

        # Look for cookie-based JWT patterns
        if "request.COOKIES.get" in perm_content:
            info["evidence"].append("cookie_authentication")
            cookie_names = re.findall(r'COOKIES\.get\(["\']([^"\']+)["\']', perm_content)
            info["token_names"] = cookie_names

        # Look for JWT patterns
        if "JWTAuthentication" in perm_content:
            info["evidence"].append("jwt_authentication")

        # Look for refresh token patterns
        if "RefreshToken" in perm_content:
            info["evidence"].append("jwt_refresh_tokens")

        return info

    def _analyze_core_permission_file(self, core_perm_content: str) -> Dict[str, Any]:
        """Analyze core/permission.py for authentication patterns."""
        info = {"evidence": [], "cookie_settings": {}}

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

    def _analyze_views_for_auth(self) -> Dict[str, Any]:
        """Analyze views.py for authentication patterns."""
        info = {"evidence": [], "response_structure": "unknown"}

        views_content = self.source_code.get("views", "")

        # Look for cookie setting in responses
        if "set_cookie" in views_content:
            info["evidence"].append("cookie_setting_in_views")

        # Extract cookie names used in set_cookie calls
        cookie_names = re.findall(r'set_cookie\(\s*key=["\']([^"\']+)["\']', views_content)
        if cookie_names:
            info["token_names"].extend(cookie_names)

        # Analyze response structure patterns
        info["response_structure"] = self._detect_response_structure(views_content)

        return info

    def _detect_login_endpoint(self) -> Dict[str, Any]:
        """Detect login endpoint from urls.py."""
        info = {"login_url": None}

        urls_content = self.source_code.get("urls", "")

        # Look for login URL patterns
        login_patterns = re.findall(
            r'path\([\'"]([^\'"]*login[^\'"]*)[\'"]', urls_content
        )
        if login_patterns:
            info["login_url"] = f"/{login_patterns[0].strip('/')}/"

        # Look for TokenObtainPairView or similar
        if "TokenObtainPairView" in urls_content:
            info["evidence"] = ["jwt_authentication"]

        return info

    def detect_response_structure(self) -> Dict[str, Any]:
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

        if "views" not in self.source_code:
            return structure_info

        views_content = self.source_code["views"]
        structure_info.update(self._detect_response_structure(views_content))

        return structure_info

    def _detect_response_structure(self, views_content: str) -> Dict[str, Any]:
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

    def extract_url_parameters(self) -> Dict[str, List[Dict[str, Any]]]:
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

        if "views" not in self.source_code:
            return url_params

        try:
            tree = ast.parse(self.source_code["views"])
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

    def analyze_permission_classes(self) -> Dict[str, Dict[str, Any]]:
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
        if "permissions" in self.source_code:
            perm_content = self.source_code["permissions"]
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

    def generate_auth_helper_method(self, auth_info: Dict[str, Any], response_structure: Dict[str, Any]) -> str:
        """
        Generate appropriate authentication helper method based on detected patterns.

        Args:
            auth_info: Authentication method detection results
            response_structure: Response structure detection results

        Returns:
            String containing the authentication helper method code
        """
        auth_method = auth_info.get("method", "none")

        if auth_method == "cookie_jwt":
            return self._generate_cookie_jwt_helper(auth_info, response_structure)
        elif auth_method == "header_jwt":
            return self._generate_header_jwt_helper(auth_info, response_structure)
        else:
            return self._generate_session_auth_helper(auth_info, response_structure)

    def _generate_cookie_jwt_helper(self, auth_info: Dict[str, Any], response_structure: Dict[str, Any]) -> str:
        """Generate cookie-based JWT authentication helper."""
        login_url = auth_info.get("login_url", "/api/login/")
        token_names = auth_info.get("token_names", ["access_token"])
        main_token = token_names[0] if token_names else "access_token"

        # Handle nested vs flat response structures
        if response_structure.get("structure_type") == "nested":
            token_access = f'response.json()["data"].get("{response_structure["token_key"]}")'
        else:
            token_access = f'response.json().get("{response_structure["token_key"]}")'

        helper_code = f'''    def authenticate_jwt(self, email, password):
        """
        Helper method to authenticate user and set JWT cookies.
        Uses cookie-based authentication as detected from the actual code.
        """
        payload = {{'email': email, 'password': password}}
        response = self.client.post(
            '{login_url}',
            data=json.dumps(payload),
            content_type='application/json'
        )
        if response.status_code == 200:
            data = response.json()
            # Handle response structure
            if isinstance(data, dict) and "data" in data:
                user_data = data["data"]
                access_token = user_data.get("{response_structure["token_key"]}")
            else:
                access_token = data.get("{response_structure["token_key"]}")

            if access_token:
                # Set cookie for subsequent requests
                self.client.cookies['{main_token}'] = access_token
                return data if isinstance(data, dict) and "data" not in data else {{'data': data, 'original_data': data}}
        return None'''

        return helper_code

    def _generate_header_jwt_helper(self, auth_info: Dict[str, Any], response_structure: Dict[str, Any]) -> str:
        """Generate header-based JWT authentication helper."""
        login_url = auth_info.get("login_url", "/api/login/")

        # Handle nested vs flat response structures
        if response_structure.get("structure_type") == "nested":
            token_access = f'response.json()["data"]["{response_structure["token_key"]}"]'
        else:
            token_access = f'response.json()["{response_structure["token_key"]}"]'

        helper_code = f'''    def authenticate_jwt(self, email, password):
        """
        Helper method to authenticate user and set JWT token in headers.
        Uses header-based authentication (Bearer token).
        """
        payload = {{'email': email, 'password': password}}
        response = self.client.post(
            '{login_url}',
            data=json.dumps(payload),
            content_type='application/json'
        )
        if response.status_code == 200:
            token = {token_access}
            if token:
                self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {{token}}'
                return response.json()
        return None'''

        return helper_code

    def _generate_session_auth_helper(self, auth_info: Dict[str, Any], response_structure: Dict[str, Any]) -> str:
        """Generate session-based authentication helper."""
        return '''    def authenticate_session(self, email, password):
        """
        Helper method to authenticate user using Django session auth.
        """
        response = self.client.post('/api/login/', {
            'email': email,
            'password': password
        })
        return response.json() if response.status_code == 200 else None'''


def integrate_enhanced_analysis(original_analyzer) -> None:
    """
    Integrate enhanced analysis capabilities into the original AppAnalyzer.

    This function adds new methods to the existing AppAnalyzer class
    without modifying the original source file.
    """
    # Add new methods to the original analyzer class
    original_analyzer.detect_authentication_method = EnhancedAppAnalyzer.detect_authentication_method
    original_analyzer.detect_response_structure = EnhancedAppAnalyzer.detect_response_structure
    original_analyzer.extract_url_parameters = EnhancedAppAnalyzer.extract_url_parameters
    original_analyzer.analyze_permission_classes = EnhancedAppAnalyzer.analyze_permission_classes
    original_analyzer.generate_auth_helper_method = EnhancedAppAnalyzer.generate_auth_helper_method

    console.print("[green]✓ Enhanced analysis methods integrated[/green]")