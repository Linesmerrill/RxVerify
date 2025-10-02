#!/usr/bin/env python3
"""
Simple test runner for RxVerify tests.
"""

import sys
import os
import subprocess
from pathlib import Path

def run_tests():
    """Run the test suite."""
    print("🧪 Running RxVerify Tests")
    print("=" * 50)
    
    # Add the project root to Python path
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))
    
    try:
        # Try to import pytest
        import pytest
        print("✅ pytest is available")
    except ImportError:
        print("❌ pytest not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pytest"])
        import pytest
        print("✅ pytest installed successfully")
    
    # Run tests
    test_dir = project_root / "tests"
    if not test_dir.exists():
        print(f"❌ Test directory not found: {test_dir}")
        return False
    
    print(f"📁 Running tests from: {test_dir}")
    
    # Run pytest
    result = pytest.main([
        str(test_dir),
        "-v",
        "--tb=short",
        "--color=yes"
    ])
    
    if result == 0:
        print("\n🎉 All tests passed!")
        return True
    else:
        print(f"\n❌ Tests failed with exit code: {result}")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
