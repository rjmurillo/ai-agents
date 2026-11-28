"""Effective CODEOWNERS coverage for changed paths.

Follows the GitHub rules the policy depends on: the last matching line wins,
a line with no owners leaves the path unowned, a leading ``/`` or an inner
``/`` anchors the pattern to the root, a bare name matches at any depth, and
a trailing ``/`` matches the directory contents.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.pr_approval.globs import glob_match


@dataclass(frozen=True)
class CodeownersRule:
    """One parsed CODEOWNERS line."""

    pattern: str
    globs: tuple[str, ...]
    owners: tuple[str, ...]


def _to_globs(raw: str) -> tuple[str, ...]:
    anchored = raw.startswith("/")
    body = raw.lstrip("/")
    directory = body.endswith("/")
    body = body.rstrip("/")
    if not body:
        return ("**",)
    if not anchored and "/" not in body:
        body = f"**/{body}"
    if directory:
        return (f"{body}/**",)
    last = body.rsplit("/", 1)[-1]
    if "*" in last or "?" in last:
        return (body,)
    # A plain name matches the file itself or everything under a directory.
    return (body, f"{body}/**")


def parse_codeowners(text: str) -> tuple[CodeownersRule, ...]:
    """Parse CODEOWNERS text into ordered rules."""
    rules: list[CodeownersRule] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        owners: list[str] = []
        for token in parts[1:]:
            if token.startswith("#"):
                break
            owners.append(token)
        rules.append(CodeownersRule(parts[0], _to_globs(parts[0]), tuple(owners)))
    return tuple(rules)


def owners_for(rules: tuple[CodeownersRule, ...], path: str) -> tuple[str, ...]:
    """Return the effective owners of ``path``; empty means unowned."""
    effective: tuple[str, ...] = ()
    for rule in rules:
        if any(glob_match(glob, path) for glob in rule.globs):
            effective = rule.owners
    return effective
