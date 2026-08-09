#!/usr/bin/env python3
"""Pure-Python markdown verifier shipped with the plugin.

Invoked by absolute path from ``invoke_markdownlint_guard.py``. Validates
markdown files using ``markdown-it-py`` (a shipped dependency) and the
co-located ``markdownlint-safe-config.yaml``. No external processes, no
registry downloads, no consumer binaries, configs, plugins, or custom rules.

Interface:
    python _markdownlint_verifier.py --markdown-lint-only -- <file> [<file>...]

Exit codes:
    0 = All files pass.
    1 = Violations found (diagnostics on stderr).
    2 = Infrastructure failure (missing dependency or config).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _check_missing_deps() -> str | None:
    """Return error message if shipped deps are unavailable."""
    try:
        import markdown_it  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        return f"shipped dependency unavailable: {exc.name}"
    return None


def _load_config(config_path: Path) -> dict[str, Any] | None:
    """Load and return the config dict, or None on failure."""
    import yaml

    try:
        text = config_path.read_text(encoding="utf-8")
        return yaml.safe_load(text) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"cannot load safe config {config_path}: {exc}", file=sys.stderr)
        return None


def _check_md041(filepath: Path, lines: list[str]) -> list[str]:
    """MD041: First line must be a heading."""
    first_non_empty = next((ln for ln in lines if ln.strip()), "")
    if not first_non_empty.startswith("#"):
        return [f"{filepath}:1 MD041/first-line-heading First line must be a heading"]
    return []


def _check_md040(filepath: Path, tokens: list[Any]) -> list[str]:
    """MD040: Fenced code blocks must specify a language."""
    violations: list[str] = []
    for tok in tokens:
        if tok.type == "fence" and not tok.info.strip():
            line = (tok.map[0] + 1) if tok.map else 0
            msg = f"{filepath}:{line} MD040/fenced-code-language Code fence missing language"
            violations.append(msg)
    return violations


def _check_md004(filepath: Path, lines: list[str]) -> list[str]:
    """MD004: List marker style must be dash."""
    violations: list[str] = []
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if stripped and stripped[0] in "*+" and len(stripped) > 1 and stripped[1] == " ":
            violations.append(f"{filepath}:{i} MD004/ul-style List marker should be dash")
    return violations


def _lint_file(filepath: Path, rules: dict[str, Any]) -> list[str]:
    """Return list of violation strings for one file."""
    from markdown_it import MarkdownIt

    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{filepath}:0 read error: {exc}"]

    lines = text.splitlines()
    md = MarkdownIt("commonmark", {"html": True})
    tokens = md.parse(text)
    violations: list[str] = []

    if rules.get("MD041") and lines:
        violations.extend(_check_md041(filepath, lines))
    if rules.get("MD040"):
        violations.extend(_check_md040(filepath, tokens))
    md004 = rules.get("MD004")
    if md004 and isinstance(md004, dict) and md004.get("style") == "dash":
        violations.extend(_check_md004(filepath, lines))

    return violations


def _parse_args(args: list[str]) -> list[str] | None:
    """Return target files or None on parse failure."""
    if "--markdown-lint-only" not in args:
        print("usage: _markdownlint_verifier.py --markdown-lint-only -- <files>", file=sys.stderr)
        return None
    try:
        sep_idx = args.index("--")
    except ValueError:
        print("missing -- separator", file=sys.stderr)
        return None
    return args[sep_idx + 1:]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    files = _parse_args(args)
    if files is None:
        return 2
    if not files:
        return 0

    dep_err = _check_missing_deps()
    if dep_err:
        print(dep_err, file=sys.stderr)
        return 2

    config_path = Path(__file__).resolve().with_name("markdownlint-safe-config.yaml")
    if not config_path.is_file():
        print(f"shipped safe config not found: {config_path}", file=sys.stderr)
        return 2

    raw_config = _load_config(config_path)
    if raw_config is None:
        return 2
    rules = raw_config.get("config", {})

    all_violations: list[str] = []
    for f in files:
        all_violations.extend(_lint_file(Path(f), rules))

    if all_violations:
        for v in all_violations:
            print(v, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
