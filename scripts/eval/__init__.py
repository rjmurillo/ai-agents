"""Evaluation scripts for agents and knowledge integration.

Entry-point CLI tools (``eval-agents.py``, ``eval-knowledge-integration.py``)
use dashes in their filenames and are invoked directly via ``python3``.
They rely on Python's default behavior of adding the script's directory to
``sys.path[0]`` so they can import the shared ``_anthropic_api`` helpers
without a package-qualified path.
"""
