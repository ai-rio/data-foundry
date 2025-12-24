#!/usr/bin/env python3
"""
Standalone test runner for basic_metrics tests that bypasses conftest.py
"""
import sys
sys.path.insert(0, '.')

import pytest
from pathlib import Path

# Run pytest on just the basic_metrics test file, bypassing conftest
sys.exit(pytest.main([
    '-v',
    '--tb=short',
    '--no-header',
    '--override-ini=python_files=test_*.py',
    '--override-ini=python_functions=test_*',
    '--override-ini=python_classes=Test*',
    'tests/unit/test_basic_metrics.py',
    '--rootdir=.',
    '-p', 'no:cacheprovider'
]))
