from dataclasses import dataclass, field
from enum import Enum


class InputType(Enum):
    GIT_URL = "git_url"
    SSH_URL = "ssh_url"
    LOCAL   = "local"


@dataclass
class ProjectSource:
    raw_input:  str
    input_type: InputType
    repo_path:  str = ""


@dataclass
class EndpointInfo:
    url_pattern:   str
    http_methods:  list[str]
    view_name:     str
    requires_auth: bool
    app_name:      str


@dataclass
class TestResult:
    endpoint:       EndpointInfo
    status:         str
    response_code:  int
    expected_code:  int
    error_message:  str | None = None
    ai_explanation: str | None = None


@dataclass
class ProjectAnalysis:
    """
    Result of analyzing a Django project before test generation.
    Discovered once, reused for all apps.
    """
    auth_type:   str         # "JWT" | "Session" | "Token" | "Unknown"
    login_url:   str         # /api/user/login/
    auth_module: str         # apps.user
    auth_app_name: str       # user

    # User model fields safe to use in create_user()
    # excludes ManyToMany fields automatically
    safe_user_fields: list[str] = field(default_factory=list)

    # Roles found in the project (if any)
    roles: list[str] = field(default_factory=list)