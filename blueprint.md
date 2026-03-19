# AI Test Runner — Phase 0 Blueprint

## Input Modes

```
┌─────────────────────────────────────────────────────────┐
│                    USER (Terminal)                      │
│                                                         │
│  Mode 1: $ ai-test-runner https://github.com/user/repo  │
│  Mode 2: $ ai-test-runner /home/user/my-django-project  │
│  Mode 3: $ ai-test-runner https://gitlab.com/user/repo  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
         CLI detects which mode it is
         and routes accordingly
```

| Mode | Input Format | Example |
|------|-------------|---------|
| GitHub URL | `https://github.com/user/repo` | `ai-test-runner https://github.com/user/repo` |
| Local folder | `/path/to/project` | `ai-test-runner /home/charitra/projects/my-django-app` |
| Git URL (non-GitHub) | `https://gitlab.com/user/repo` | `ai-test-runner https://gitlab.com/user/repo` |

---

## Full Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MODULE 1: CLI Entry Point                 │
│                                                              │
│  - Accepts one argument: url_or_path                         │
│  - Detects input type:                                       │
│      → starts with https/http  = Git remote URL             │
│      → starts with / or ./     = Local path                 │
│      → starts with git@        = SSH Git URL                │
│  - Validates accordingly                                     │
│  - Passes to Repo Handler with input_type flag               │
└──────────────────────────┬───────────────────────────────────┘
                           │  { source, input_type }
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   MODULE 2: Repo Handler                     │
│                                                              │
│  if input_type == "git_url":                                 │
│      → Clone via GitPython into /tmp/ai-tester/<repo_name>  │
│      → Supports GitHub, GitLab, Bitbucket, any git remote   │
│                                                              │
│  if input_type == "local_path":                              │
│      → Validate path exists on disk                         │
│      → Validate it's a Django project (manage.py check)     │
│      → Use directly, NO cloning needed                      │
│      → Works on your own machine, safe read-only mode        │
│                                                              │
│  OUTPUT → repo_path (same for both modes)                   │
│  (Everything after this module is identical)                │
└──────────────────────────┬───────────────────────────────────┘
                           │  repo_path: str
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  MODULE 3: Endpoint Scanner                  │
│  (Same regardless of input mode)                            │
│  - Finds manage.py                                           │
│  - Reads all urls.py recursively                             │
│  - Detects DRF Routers, ViewSets, APIViews, FBVs             │
└──────────────────────────┬───────────────────────────────────┘
                           │  endpoints: list[EndpointInfo]
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  MODULE 4: Test Generator                    │
│  - Rule-based templates (MVP)                                │
│  - AI-assisted via Claude / OpenAI (Advanced)               │
└──────────────────────────┬───────────────────────────────────┘
                           │  test_files: list[str]
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   MODULE 5: Test Runner                      │
│                                                              │
│  if input was git_url (cloned):                             │
│      → Full isolated venv + install requirements.txt         │
│                                                              │
│  if input was local_path:                                    │
│      → Option A: Use existing venv of the project            │
│      → Option B: Create fresh venv (safer)                  │
│      → Option C: Docker container (safest)                  │
└──────────────────────────┬───────────────────────────────────┘
                           │  results: list[TestResult]
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   MODULE 6: Report Module                    │
│  - Pass / Fail summary                                       │
│  - Error messages + AI explanation                           │
│  - Export to JSON / PDF (Advanced)                           │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Structures

```python
from dataclasses import dataclass
from enum import Enum

class InputType(Enum):
    GIT_URL   = "git_url"    # https://github.com/... or https://gitlab.com/...
    SSH_URL   = "ssh_url"    # git@github.com:user/repo.git
    LOCAL     = "local"      # /home/charitra/projects/my-app

@dataclass
class ProjectSource:
    raw_input: str           # exactly what the user typed
    input_type: InputType    # detected type
    repo_path: str           # resolved local path after handling

@dataclass
class EndpointInfo:
    url_pattern: str         # e.g. "/api/users/"
    http_methods: list[str]  # e.g. ["GET", "POST"]
    view_name: str           # e.g. "UserListView"
    requires_auth: bool      # detected from permission_classes
    app_name: str            # which Django app it belongs to

@dataclass
class TestResult:
    endpoint: EndpointInfo
    status: str              # "PASSED" | "FAILED" | "ERROR"
    response_code: int
    expected_code: int
    error_message: str | None
    ai_explanation: str | None
```

---

## Input Detection Logic

```python
def detect_input_type(source: str) -> InputType:
    if source.startswith("git@"):
        return InputType.SSH_URL
    elif source.startswith("http://") or source.startswith("https://"):
        return InputType.GIT_URL
    elif source.startswith("/") or source.startswith("./") or source.startswith("~"):
        return InputType.LOCAL
    else:
        raise ValueError(f"Cannot detect input type for: {source}")
```

---

## CLI Usage Examples

```bash
# Mode 1 — GitHub URL
$ ai-test-runner https://github.com/charitra/brilliant-sagarmatha

# Mode 2 — GitLab or any Git remote
$ ai-test-runner https://gitlab.com/someuser/django-project

# Mode 3 — Your own local project folder
$ ai-test-runner /home/charitra/projects/brilliant-sagarmatha
$ ai-test-runner ./my-django-app
$ ai-test-runner ~/projects/lbef-portal
```

---

## Folder Structure

```
ai-django-tester/
│
├── ai_tester/
│   ├── __init__.py
│   ├── cli.py                  # Module 1 — Entry, input detection
│   ├── repo_handler.py         # Module 2 — Clone OR use local path
│   │   ├── git_cloner.py       #   └─ handles remote git URLs
│   │   └── local_resolver.py   #   └─ handles local paths
│   ├── endpoint_scanner.py     # Module 3 — URL detection
│   ├── test_generator.py       # Module 4 — Test creation
│   ├── test_runner.py          # Module 5 — Safe execution
│   ├── report.py               # Module 6 — Output formatting
│   └── ai_helper.py            # Module 7 — AI layer (optional)
│
├── tests/
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Phase Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Blueprint | ✅ Done |
| Phase 1 | Module 1: CLI + Input Detection (3 modes) | ⬜ |
| Phase 2 | Module 2: Repo Handler | ⬜ |
| Phase 2a | &nbsp;&nbsp;&nbsp;&nbsp;Git URL cloner | ⬜ |
| Phase 2b | &nbsp;&nbsp;&nbsp;&nbsp;Local path resolver | ⬜ |
| Phase 3 | Module 3: Endpoint Scanner | ⬜ |
| Phase 4 | Module 4: Test Generator | ⬜ |
| Phase 5 | Module 5: Test Runner | ⬜ |
| Phase 6 | Module 6: Report | ⬜ |
| Phase 7 | Module 7: AI Layer | ⬜ |
| Phase 8 | Polish (export, CI/CD, parallel) | ⬜ |