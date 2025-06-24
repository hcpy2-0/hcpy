#!/usr/bin/env python3
"""
Test runner script for HADiscovery tests
"""

import sys
import subprocess
import os

def main():
    """Run the test suite"""

    # Check if we're in the right directory
    if not os.path.exists('HADiscovery.py'):
        print("Error: HADiscovery.py not found. Please run from the project root.")
        sys.exit(1)

    # Check if tests directory exists
    if not os.path.exists('tests'):
        print("Error: tests directory not found.")
        sys.exit(1)

    # Install test dependencies if needed
    try:
        import pytest
    except ImportError:
        print("Installing test dependencies...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'tests/requirements-test.txt'])

    # Run the tests
    print("Running HADiscovery tests...")
    result = subprocess.run([
        sys.executable, '-m', 'pytest',
        'tests/',
        '-v',
        '--tb=short'
    ])

    if result.returncode == 0:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()
