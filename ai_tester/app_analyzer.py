import ast
import re
from pathlib import Path
from typing import Dict, List, Any
from rich.console import Console
from ai_tester.ai_helper import AIHelper

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


    def __init__(self, repo_path: str, ai_helper: AIHelper):
        self.repo_path = Path(repo_path)
        self.ai_helper = ai_helper

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

        # Parse and extract structured information
        structured_analysis = self._parse_app_structure(app_dir, source_code, app_endpoints)

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
                                    "required": self._is_field_required(item, source),
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
                                    "required": self._is_field_required(item, source),
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

    def _is_field_required(self, assign_node: ast.Assign, source: str) -> bool:
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

        try:
            response = self.ai_helper.client.chat.completions.create(
                model=self.ai_helper.MODEL,
                max_tokens=self.MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            ai_generated_prompt = response.choices[0].message.content

            # Clean the response
            ai_generated_prompt = ai_generated_prompt.strip()
            if ai_generated_prompt.startswith("```"):
                ai_generated_prompt = ai_generated_prompt.split("```")[1].strip()
            if ai_generated_prompt.startswith("prompt"):
                ai_generated_prompt = ai_generated_prompt[6:].strip()

            console.print(f"    [green]✓ AI prompt generated ({len(ai_generated_prompt)} chars)[/green]")
            return ai_generated_prompt

        except Exception as e:
            console.print(f"    [red]✗ Failed to generate AI prompt: {e}[/red]")
            # Fallback to a basic prompt
            return self._fallback_prompt(app_name, analysis)

    def _build_analysis_context(self, app_name: str, analysis: Dict[str, Any]) -> str:
        """Build a readable analysis context string."""
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
