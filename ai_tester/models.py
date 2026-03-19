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
    repo_path:  str = ""   # filled after repo_handler resolves it


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
    status:         str            # "PASSED" | "FAILED" | "ERROR"
    response_code:  int
    expected_code:  int
    error_message:  str | None = None
    ai_explanation: str | None = None