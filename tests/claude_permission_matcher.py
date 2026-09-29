"""Model of Claude Code's `permissions.deny` matcher for Bash rules.

Shared by the test modules that pin `.claude/settings.json` deny rules, so one
matcher model backs every assertion. Each consuming module keeps its own
negative control proving the matcher still fires on the rules it relies on.

Matcher contract, from https://code.claude.com/docs/en/permissions:

- "Bash rules match the whole command text, with `*` standing in for any text."
- "A deny or ask rule matches past any leading assignment."
- Compound commands split on `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines, and
  a rule "must match each subcommand independently".
- A fixed wrapper set is stripped before matching.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

# Separators for compound commands. This regex is NOT shell-quote aware:
# it splits at semicolons and pipes even inside single/double quotes. The
# test commands in this file are deliberately kept free of quoted separators
# so this limitation does not produce false results. A shell-aware parser
# would be more correct but also more complex; the deny rules themselves
# operate on the full command string, not on parsed subcommands.
_SEPARATORS = re.compile(r"\|\&|\&\&|\|\||[;|&\n]")

# Wrappers Claude Code strips before matching, each of which runs its argument
# as the real command.
_WRAPPERS = frozenset(
    {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin", "noglob"}
)

# `NAME=value` prefixes. Deny rules match past these.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")

# Wrappers that take a positional argument of their own before the real
# command: `timeout 30 git ...`, `nice 10 git ...`. Stripping the wrapper alone
# would leave that argument at the head and defeat the anchored literal.
_WRAPPERS_WITH_OPERAND = frozenset({"timeout", "nice"})
_DURATION = re.compile(r"^-?\d+(\.\d+)?[smhd]?$")


def _rule_body(rule: str) -> str | None:
    """Return the pattern inside `Bash(...)`, or None for a non-Bash rule."""
    match = re.fullmatch(r"Bash\((.*)\)", rule, re.DOTALL)
    return match.group(1) if match else None


def _normalize(command: str) -> str:
    """Strip the wrappers and leading assignments the reference strips."""
    tokens = command.split()
    while tokens:
        head = tokens[0]
        if _ASSIGNMENT.fullmatch(head):
            tokens = tokens[1:]
            continue
        if head in _WRAPPERS:
            tokens = tokens[1:]
            # Drop the wrapper's own flags, then its operand where it takes one.
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
            if head in _WRAPPERS_WITH_OPERAND:
                # `timeout -k 5 30s cmd` leaves two numeric operands once the
                # flags are gone, so consume every numeric token, not just one.
                while tokens and _DURATION.fullmatch(tokens[0]):
                    tokens = tokens[1:]
            continue
        # Bare `xargs` is stripped; `xargs` carrying flags is not.
        if head == "xargs" and len(tokens) > 1 and not tokens[1].startswith("-"):
            tokens = tokens[1:]
            continue
        break
    return " ".join(tokens)


def _pattern_matches(pattern: str, command: str) -> bool:
    """Apply one Bash rule pattern to one already-normalized subcommand."""
    regex = "".join(".*" if part == "*" else re.escape(part) for part in re.split(r"(\*)", pattern))
    if re.fullmatch(regex, command):
        return True
    # "A `*` at the end, with a space before it, also matches the bare command",
    # but only when that trailing `*` is the rule's only wildcard.
    if pattern.endswith(" *") and pattern.count("*") == 1:
        return command == pattern[:-2]
    return False


def _denied_by(command: str, rules: list[str]) -> list[str]:
    """Every rule in *rules* that blocks *command*.

    A deny rule matching any single subcommand blocks the whole compound
    command, so this checks each subcommand against each rule.
    """
    subcommands = [_normalize(part.strip()) for part in _SEPARATORS.split(command)]
    return [
        rule
        for rule in rules
        if (body := _rule_body(rule)) is not None
        and any(sub and _pattern_matches(body, sub) for sub in subcommands)
    ]


def _deny_rules() -> list[str]:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]["deny"]
