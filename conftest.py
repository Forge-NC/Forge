"""Pytest configuration for the Forge test suite.

Three files under tests/ are standalone validation scripts, not pytest modules: each calls
sys.exit() at import time (printing its own PASS/FAIL), which crashes pytest collection for
the whole session. They are run directly in CI (python tests/<name>.py), so we exclude them
from pytest collection here. The rest of the suite then collects and runs cleanly.
"""
collect_ignore = [
    "tests/test_break_axis.py",
    "tests/test_must_refuse.py",
    "tests/test_oracle_parity.py",
]
