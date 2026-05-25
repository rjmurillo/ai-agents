"""Pytest configuration for memory skill.

Prevents pytest from collecting source modules whose function names
start with 'test_' (e.g., test_schema_valid, test_forgetful_available).
"""

collect_ignore_glob = ["memory_core/*.py"]
