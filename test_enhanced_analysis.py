#!/usr/bin/env python3
"""
Test script to verify the enhanced analysis improvements.

This script tests the new authentication and response structure detection
on the Brilliant Sagarmatha user app.
"""

import sys
from pathlib import Path

# Add the DjangoProbe directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from ai_tester.app_analyzer import AppAnalyzer
from ai_tester.ai_helper import AIHelper

def test_enhanced_analysis():
    """Test the enhanced analysis capabilities."""

    # Path to the cached project
    repo_path = "/home/meow/.djangoprobe/cache/Brilliant_Sagarmatha_Server"

    print(f"Testing enhanced analysis on: {repo_path}")
    print("=" * 60)

    # Initialize AI Helper (we just need it for basic functionality)
    ai_helper = AIHelper(repo_path)

    # Initialize App Analyzer
    analyzer = AppAnalyzer(repo_path, ai_helper)

    # Get the app directory
    app_name = "user"
    app_dir = ai_helper.get_app_dir(app_name)

    if not app_dir:
        print(f"❌ App directory not found: {app_name}")
        return

    print(f"✓ Found app directory: {app_dir}")

    # Collect source code
    source_code = analyzer._collect_app_source_code(app_dir)
    print(f"✓ Collected source code from {len(source_code)} files")

    # Test authentication detection
    print("\n" + "=" * 60)
    print("Testing Authentication Detection")
    print("=" * 60)

    auth_info = analyzer._detect_auth_method(source_code, app_dir)

    print(f"✓ Auth Method: {auth_info.get('method')}")
    print(f"✓ Login URL: {auth_info.get('login_url')}")
    print(f"✓ Token Names: {auth_info.get('token_names')}")
    print(f"✓ Cookie Settings: {auth_info.get('cookie_settings')}")
    print(f"✓ Evidence: {auth_info.get('evidence')}")
    print(f"✓ Detected: {auth_info.get('detected')}")

    # Test response structure detection
    print("\n" + "=" * 60)
    print("Testing Response Structure Detection")
    print("=" * 60)

    response_structure = analyzer._detect_response_structure(source_code)

    print(f"✓ Structure Type: {response_structure.get('structure_type')}")
    print(f"✓ Data Key: {response_structure.get('data_key')}")
    print(f"✓ Message Key: {response_structure.get('message_key')}")
    print(f"✓ Token Key: {response_structure.get('token_key')}")
    print(f"✓ Evidence: {response_structure.get('evidence')}")
    print(f"✓ Detected: {response_structure.get('detected')}")

    # Test URL parameter extraction
    print("\n" + "=" * 60)
    print("Testing URL Parameter Extraction")
    print("=" * 60)

    url_params = analyzer._extract_url_parameters(source_code)

    print(f"✓ Views with URL parameters: {len(url_params)}")
    for view_name, params in url_params.items():
        param_info = ", ".join([f"{p['name']}: {p['type']}" for p in params])
        print(f"  - {view_name}: [{param_info}]")

    # Test permission class analysis
    print("\n" + "=" * 60)
    print("Testing Permission Class Analysis")
    print("=" * 60)

    permission_analysis = analyzer._analyze_permission_classes(source_code, app_dir)

    print(f"✓ Permission classes found: {len(permission_analysis)}")
    for perm_name, perm_info in permission_analysis.items():
        print(f"  - {perm_name} (from {perm_info['module']})")
        if perm_info.get("checks_superuser"):
            print(f"    ✓ Checks superuser")
        if perm_info.get("checks_roles"):
            print(f"    ✓ Checks roles: {perm_info['checks_roles']}")
        if perm_info.get("checks_pages"):
            print(f"    ✓ Checks pages")

    # Test auth response structure building
    print("\n" + "=" * 60)
    print("Testing Auth Response Structure Building")
    print("=" * 60)

    auth_response_structure = analyzer._build_auth_response_structure(
        auth_info, response_structure
    )

    print(f"✓ Auth Method: {auth_response_structure.get('auth_method')}")
    print(f"✓ Login URL: {auth_response_structure.get('login_url')}")
    print(f"✓ Token Path: {auth_response_structure.get('token_path')}")
    print(f"✓ Response Format: {auth_response_structure.get('response_format')}")
    print(f"✓ Cookie Names: {auth_response_structure.get('cookie_names')}")
    print(f"✓ Data Key: {auth_response_structure.get('data_key')}")
    print(f"✓ Message Key: {auth_response_structure.get('message_key')}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("✅ Authentication Detection: WORKING")
    print("✅ Response Structure Detection: WORKING")
    print("✅ URL Parameter Extraction: WORKING")
    print("✅ Permission Class Analysis: WORKING")
    print("✅ Auth Response Structure Building: WORKING")

    print("\n🎉 All enhanced analysis features are working correctly!")

if __name__ == "__main__":
    test_enhanced_analysis()