"""
DjangoProbe - AI-powered Django API test runner.

This package provides intelligent endpoint discovery, test generation,
and test execution for Django projects.
"""

from ai_tester.models import (
    InputType,
    ProjectSource,
    EndpointInfo,
    TestResult,
    ProjectAnalysis,
)

from ai_tester.endpoint_scanner import EndpointScanner
from ai_tester.repo_handler import RepoHandler
from ai_tester.enhanced_test_generator import EnhancedTestGenerator
from ai_tester.project_analyzer import ProjectAnalyzer
from ai_tester.app_analyzer import AppAnalyzer
from ai_tester.app_test_runner import AppTestRunner
from ai_tester.report import ReportGenerator
from ai_tester.ai_helper import AIHelper

__all__ = [
    # Models
    "InputType",
    "ProjectSource",
    "EndpointInfo",
    "TestResult",
    "ProjectAnalysis",
    # Core Components
    "EndpointScanner",
    "RepoHandler",
    "EnhancedTestGenerator",
    "ProjectAnalyzer",
    "AppAnalyzer",
    "AppTestRunner",
    "ReportGenerator",
    "AIHelper",
]

__version__ = "2.0.0"
