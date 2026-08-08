#!/usr/bin/env python3
"""Gate: subprocess calls with text-mode UTF-8 must pair errors="replace".

A ``subprocess.run`` (or any ``subprocess.*`` call) that sets both
``encoding="utf-8"`` (case-insensitive, common aliases accepted) and
text-capturing mode (``text=True`` or ``capture_output=True``) must also
pass ``errors="replace"``.

Without ``errors="replace"``, a child process that emits bytes invalid for
UTF-8 raises ``UnicodeDecodeError`` on the calling side. On Windows CI
runners, ``git`` and ``gh`` can emit such bytes in branch names, commit
messages, or file-system paths. The decode fails before the caller can
report the real assertion, hiding the underlying failure. See issue #4261.

Canonical house pattern (in ``scripts/ci/verify_code_env.py``):

    subprocess.run(
        argv,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

What this scanner checks:
    A call is flagged when ALL of these hold:
    1. It reaches a subprocess text-capturing entry point (``subprocess.run``,
       ``subprocess.check_output``, ``subprocess.Popen``,
       ``subprocess.check_call``).
    2. It has a literal ``encoding=`` keyword whose value is a UTF-8 alias
       (``"utf-8"``, ``"utf8"``, ``"UTF-8"``, ``"UTF8"``, ``"utf_8"``).
    3. The call enables text mode: ``text=True`` or ``capture_output=True``
       are present as literal ``True``-valued keywords, or the entry point
       decodes unconditionally (``check_output``).
    4. No ``errors=`` keyword is present.

Deliberate over-approximation:
    When a call site uses ``**kwargs``, we cannot know whether ``errors`` was
    supplied by the caller. Rather than silently wave it through, we flag the
    site. The author must either add ``errors="replace"`` or restructure to
    avoid the splat. One extra keyword in the rare-but-valid call is worth
    never missing a decode on the common violating call.

Exits (ADR-035):
    0 - No violations found.
    1 - One or more violations detected.
    2 - Configuration error (invalid repository root).
"""

from __future__ import annotations

import ast
import os
import stat
import subprocess
import sys
from pathlib import Path

_UTF8_ALIASES: frozenset[str] = frozenset({"utf-8", "utf8", "utf_8", "UTF-8", "UTF8", "UTF_8"})

# subprocess entry points that accept keyword arguments
_TEXT_CAPTURING_CALLS: frozenset[str] = frozenset({"run", "Popen", "check_call"})

# Entry points that unconditionally return decoded text (no text= needed)
_UNCONDITIONAL_DECODE_CALLS: frozenset[str] = frozenset({"check_output", "getoutput"})

_ALL_SUBPROCESS_CALLS: frozenset[str] = _TEXT_CAPTURING_CALLS | _UNCONDITIONAL_DECODE_CALLS


def _keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for the first keyword matching ``name``, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_true_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value is True


def _is_utf8_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value in _UTF8_ALIASES


def _is_subprocess_pipe(node: ast.expr | None) -> bool:
    """Return whether *node* names ``subprocess.PIPE``."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "subprocess"
        and node.attr == "PIPE"
    )


def _subprocess_call_name(
    node: ast.Call,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
) -> str | None:
    """Return the bare function name for a ``subprocess.*`` call, or None."""
    func = node.func
    # subprocess.run(...) or an imported module alias such as sp.run(...)
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in module_aliases
        and func.attr in _ALL_SUBPROCESS_CALLS
    ):
        return func.attr
    # from subprocess import run; run(...), imported aliases, or direct rebinding.
    if isinstance(func, ast.Name):
        return callable_aliases.get(func.id)
    return None


def _record_import_bindings(
    node: ast.AST,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
) -> None:
    """Add subprocess bindings declared by one import node."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "subprocess":
                module_aliases.add(alias.asname or alias.name)
        return
    if not isinstance(node, ast.ImportFrom) or node.module != "subprocess":
        return
    for alias in node.names:
        if alias.name in _ALL_SUBPROCESS_CALLS:
            callable_aliases[alias.asname or alias.name] = alias.name


def _resolve_assignment_binding(
    node: ast.AST,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
) -> tuple[str, str] | None:
    """Resolve one simple callable rebinding, if present."""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    if not isinstance(target, ast.Name):
        return None
    value = node.value
    if (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id in module_aliases
        and value.attr in _ALL_SUBPROCESS_CALLS
    ):
        return target.id, value.attr
    if isinstance(value, ast.Name) and value.id in callable_aliases:
        return target.id, callable_aliases[value.id]
    return None


def _subprocess_bindings(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    """Return module and callable aliases that resolve to subprocess entry points."""
    module_aliases = {"subprocess"}
    callable_aliases = {name: name for name in _ALL_SUBPROCESS_CALLS}
    nodes = list(ast.walk(tree))

    for node in nodes:
        _record_import_bindings(node, module_aliases, callable_aliases)

    changed = True
    while changed:
        changed = False
        for node in nodes:
            binding = _resolve_assignment_binding(
                node, module_aliases, callable_aliases
            )
            if binding is None:
                continue
            name, resolved = binding
            if callable_aliases.get(name) != resolved:
                callable_aliases[name] = resolved
                changed = True
    return module_aliases, callable_aliases


def _is_flagged(
    call: ast.Call,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
) -> bool:
    """Return True when this call violates the errors="replace" convention.

    A call is flagged when it reaches a subprocess text entry point, pins
    UTF-8 as the codec, enables text mode, and omits ``errors=``.
    """
    name = _subprocess_call_name(call, module_aliases, callable_aliases)
    if name is None:
        return False

    encoding_node = _keyword_value(call, "encoding")
    if not _is_utf8_literal(encoding_node):
        # No explicit UTF-8 pin: not in scope for this checker.
        return False

    # Verify text mode is enabled (or the call decodes unconditionally).
    unconditional = name in _UNCONDITIONAL_DECODE_CALLS
    text_enabled = (
        _is_true_literal(_keyword_value(call, "text"))
        or _is_true_literal(_keyword_value(call, "capture_output"))
        or _is_subprocess_pipe(_keyword_value(call, "stdout"))
        or _is_subprocess_pipe(_keyword_value(call, "stderr"))
    )
    if not unconditional and not text_enabled:
        # Binary mode with an explicit encoding is unusual but not our concern.
        return False

    # Only replacement decoding satisfies the convention. Strict decoding must
    # use the line-scoped suppression marker when failure is intentional.
    errors_node = _keyword_value(call, "errors")
    if (
        isinstance(errors_node, ast.Constant)
        and errors_node.value == "replace"
    ):
        return False

    # A **kwargs splat may carry errors= but we cannot verify; flag conservatively.
    # This is the deliberate over-approximation described in the module docstring.
    return True


_SUPPRESSION_COMMENT = "# subprocess-encoding: strict-ok"


class ScanError(RuntimeError):
    """Raised when the gate cannot inspect its declared source corpus."""


def _clean_git_env() -> dict[str, str]:
    """Return the process environment without ambient Git repository pointers."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }


def find_violations(source: str, filename: str = "<string>") -> list[int]:
    """Return line numbers of flagged calls in *source*.

    A call on a line that ends with ``# subprocess-encoding: strict-ok`` is
    suppressed. Use this only when strict decoding is intentional and
    documented (for example, when the stream is guaranteed valid UTF-8 and a
    decode failure should propagate as an error rather than silently produce
    replacement characters).
    """
    tree = ast.parse(source, filename=filename)
    module_aliases, callable_aliases = _subprocess_bindings(tree)

    source_lines = source.splitlines()

    def _suppressed(lineno: int) -> bool:
        if lineno < 1 or lineno > len(source_lines):
            return False
        return _SUPPRESSION_COMMENT in source_lines[lineno - 1]

    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _is_flagged(node, module_aliases, callable_aliases)
        and not _suppressed(node.lineno)
    )


def _collect_sources(repo_root: Path) -> list[Path]:
    """Return tracked Python files under ``scripts/`` that are not in cache dirs."""
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "-z",
                "scripts/*.py",
                "scripts/**/*.py",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=_clean_git_env(),
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScanError(f"git could not list tracked scripts: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"git exited {completed.returncode}"
        raise ScanError(f"git could not list tracked scripts: {detail}")

    rels = [entry for entry in completed.stdout.split("\0") if entry]
    sources = [repo_root / rel for rel in rels if rel.endswith(".py")]
    if not sources:
        raise ScanError("git reported zero tracked Python files under scripts/")
    return sources


def _scan_all(repo_root: Path) -> tuple[list[tuple[Path, int]], int]:
    """Return violations and the number of tracked source files examined."""
    sources = _collect_sources(repo_root)
    results: list[tuple[Path, int]] = []
    for path in sources:
        try:
            mode = path.stat(follow_symlinks=False).st_mode
        except OSError as exc:
            raise ScanError(f"tracked source is missing: {path}") from exc
        if not stat.S_ISREG(mode):
            raise ScanError(f"tracked source is not a regular file: {path}")
        try:
            source = path.read_text(encoding="utf-8")
            lines = find_violations(source, str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise ScanError(f"could not analyze tracked source {path}: {exc}") from exc
        for lineno in lines:
            results.append((path, lineno))
    return results, len(sources)


def find_all_violations(repo_root: Path) -> list[tuple[Path, int]]:
    """Return ``(path, lineno)`` pairs for every flagged call site."""
    return _scan_all(repo_root)[0]


def validate_subprocess_encoding(repo_root: Path) -> bool:
    """Return True when no violation is found.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used
    by ``pre_pr_sequence.py``.
    """
    violations, scanned_files = _scan_all(repo_root)
    if not violations:
        print(
            f"[OK] Scanned {scanned_files} tracked Python file(s) under scripts/; "
            "0 subprocess encoding violations."
        )
        return True
    count = len(violations)
    print(
        f"[FAIL] {count} subprocess call(s) in {scanned_files} tracked file(s) "
        'pin UTF-8 encoding without errors="replace":',
        file=sys.stderr,
    )
    for path, lineno in violations:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}:{lineno}", file=sys.stderr)
    print(
        '\nFix: add errors="replace" to each flagged call.',
        file=sys.stderr,
    )
    print(
        "Reason: a child process on Windows can emit bytes invalid for UTF-8.",
        file=sys.stderr,
    )
    print(
        'Without errors="replace", the decode raises before the caller can report '
        "the real failure.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        return 0 if validate_subprocess_encoding(repo_root) else 1
    except ScanError as exc:
        print(f"[FAIL] Subprocess encoding scan did not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
