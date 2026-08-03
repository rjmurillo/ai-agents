#!/usr/bin/env python3
"""Interpreter-portability ratchet for documented script invocations (issue #3791).

A document that tells a contributor to run
doc-interpreter-portability: the defect this guard finds, quoted so it can be named
    python3 scripts/sync_adr_protocol.py
is only correct on a machine whose *system* interpreter already has the script's
third-party dependencies. ``scripts/sync_adr_protocol.py:24`` is ``import yaml``
and PyYAML is a declared project dependency (``pyproject.toml``), not a stdlib
module, so on a clean checkout the documented command dies with::
    ModuleNotFoundError: No module named 'yaml'
The portable form names the project environment::
    uv run python scripts/sync_adr_protocol.py
Why a docs guard and not a code fix:
  PR #3793 tried to delete the ``import yaml`` by hand-rolling a scalar reader.
  It was closed unmerged after review measured six behavioral divergences from
  ``yaml.safe_load`` on a script that decides ADR lifecycle state. The settled
  resolution is to name the right interpreter in the docs, which carries no
  behavioral risk. This guard keeps that fix from silently regressing.

What it counts:
  A ``python``/``python3`` invocation, optionally with short options
  (``python3 -u ...``), of a **tracked** ``.py`` file whose module-level import
  closure reaches a module that is neither stdlib
  (``sys.stdlib_module_names``) nor another tracked module in this repository.
  Module-level is the operative word. ``scripts/eval/eval-suite.py`` imports
  ``_anthropic_api``, which imports ``anthropic`` inside a function body. That
  import does not run on the documented ``--dry-run`` path, and
  ``python3 -S scripts/eval/eval-suite.py --dry-run`` succeeds, so counting it
  would be a false positive. Only imports that execute at import time count:
  the module body, plus ``if``/``try``/``with``/``for`` and class bodies nested
  in it, never a function body.
  An invocation already prefixed with ``uv run`` does NOT match; that is the
  fixed form. ``#!/usr/bin/env python3`` shebangs do not match (no ``.py``
  operand). Hook registrations such as
  ``python3 -u .claude/hooks/<EventName>/invoke_<purpose>.py`` do not match:
  the placeholder path is not a tracked file, and hooks run under the host's
  ambient interpreter by contract (``.claude/rules/python.md``).

Scope:
  Tracked Markdown **and Python**, minus three exclusions.
  Python is in scope because a usage block in a module docstring, and a
  remediation string a script prints to a contributor's terminal, hand over the
  same unrunnable command a Markdown instruction does.
  ``build/generate_agents.py`` printed a "To fix: Run ..." line naming the bare
  interpreter on every drift failure, which is the exact command that dies on a
  clean checkout.
  * **Historical roots** (``.agents/sessions/``, ``.agents/retrospective/``,
    ``.agents/architecture/``, and siblings). These are records of what was
    decided or done, not instructions to follow. Rewriting a session log or an
    ADR body to change a command it quotes would falsify the record.
  * **Generated mirrors** (``src/copilot-cli/``, ``src/vs-code-agents/``,
    ``.github/instructions/``). ``.agents/governance/GENERATOR-FILES.md`` names
    a generator for each: ``generate_skills.py``/``generate_commands.py`` and
    ``_build_lib`` write ``src/copilot-cli/``, ``generate_agents.py`` writes
    ``src/vs-code-agents/``, ``generate_rules.py`` writes
    ``.github/instructions/``. The fix belongs in the canonical source and
    arrives here by regeneration.
    ``src/claude/`` is deliberately NOT on that list. It looks like a mirror and
    is not one. GENERATOR-FILES.md:35 says so in as many words: "``src/claude/``
    is a hand-maintained copy, not a generator output. It was misclassified as a
    strict vendored copy until Issue #2882". No generator writes it, and
    ``build/scripts/validate_install_parity.py:97`` blocklists ``AGENTS.md``
    from every parity group, so ``src/claude/AGENTS.md`` had no gate of any kind.
    Excluding it here is what let five bare-interpreter instances survive two
    rounds of this fix (``src/claude/AGENTS.md`` lines 61, 70, 279, 294, 305).
  * **``tests/``**. Test files construct offending invocations on purpose, as
    fixtures for this guard and for its siblings. Same carve-out shape as the
    ``tests/hooks/fixtures/`` exemption in ``.claude/rules/universal.md``.
Declaring a single line:
  A line carrying ``doc-interpreter-portability:`` plus a reason, on the offense
  itself or on the line directly above it, is skipped. Two live cases, both
  quoting what CI runs verbatim under ``.claude/rules/canonical-source-mirror.md``
  (CI installs the dependencies system-wide, so bare ``python3`` is correct
  there and rewording the quote would falsify the citation). Line-scoped on
  purpose: a whole-file opt-out is what this guard's own ``src/claude/``
  exclusion was, and it hid five real offenses.
Baseline ratchet:
  ``doc_interpreter_baseline.json`` grandfathers per-file counts, and it is
  **empty**. Every in-scope file was migrated in the same change that added this
  guard, and the Python surface plus ``src/claude/AGENTS.md`` in the change that
  widened it. So any offense at all is a regression, and the check FAILS on it.
  Keep the baseline empty. ``--update-baseline`` exists to tighten a count after
  a fix, never to admit a new offender; adding an entry also breaks
  ``test_repository_has_no_documented_bare_interpreter_invocations``.

Exit codes (ADR-035):
  0 - no drift (counts at or below baseline), or --update-baseline wrote the file
  1 - drift detected (a file exceeds its baseline or a new file offends)
  2 - configuration error (baseline unreadable, git unavailable)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

from scripts.validation.doc_interpreter_subprocess import python_subprocess_targets

_DEFAULT_BASELINE_NAME = "doc_interpreter_baseline.json"

# Records, not instructions. A command quoted inside one of these describes what
# was run at the time; changing it would rewrite the record.
HISTORICAL_ROOTS: tuple[str, ...] = (
    ".agents/analysis/",
    ".agents/archive/",
    ".agents/architecture/",
    ".agents/audit/",
    ".agents/audits/",
    ".agents/critique/",
    ".agents/devops/",
    ".agents/planning/",
    ".agents/projects/",
    ".agents/qa/",
    ".agents/retrospective/",
    ".agents/sessions/",
    ".agents/specs/",
    ".claude-mem/",
    ".forgetful/",
    ".serena/",
    "evals/",
)

# Build outputs per .agents/governance/GENERATOR-FILES.md, which names a
# generator for each. Fix the source; these arrive by regeneration.
#
# `src/claude/` is NOT here, though it sits beside two roots that are. The same
# file says so directly (GENERATOR-FILES.md:35): "`src/claude/` is a
# hand-maintained copy, not a generator output. It was misclassified as a strict
# vendored copy until Issue #2882". Listing it cost five real offenses in
# `src/claude/AGENTS.md`, which nothing else guards either:
# `validate_install_parity.py:97` blocklists `AGENTS.md` from every parity group.
GENERATED_ROOTS: tuple[str, ...] = (
    ".github/instructions/",
    "src/copilot-cli/",
    "src/vs-code-agents/",
)

# Test files build offending invocations on purpose, as fixtures for this guard
# and its siblings. Same shape as the `tests/hooks/fixtures/` carve-out in
# `.claude/rules/universal.md`.
FIXTURE_ROOTS: tuple[str, ...] = ("tests/",)

# A line-scoped opt-out. Put it on the offending line or the line directly above,
# with a reason. Line-scoped rather than file-scoped because a file-scoped
# opt-out is exactly what the `src/claude/` entry above used to be.
DECLARATION = "doc-interpreter-portability:"

# `python[3] [short opts] <tracked>.py`
#
# The `\.{0,2}/?` prefix on the path is load-bearing. Without it the operand had
# to start with a word character, so every documented invocation of a script
# under a dot-directory was invisible: `python3 .claude/skills/adr-review/
# scripts/detect_adr_changes.py` (which is `import yaml`) went unreported, and so
# did `./scripts/<name>.py`, which made the `./` strip in `find_offenses` dead
# code. Seven offenses across four files hid behind that one character class.
INVOCATION_PATTERN = re.compile(
    r"(?<![\w./-])"
    r"python3?"
    r"(?:[ \t]+-[\w-]+)*"
    r"[ \t]+"
    r"(?P<path>\.{0,2}/?[A-Za-z0-9_][A-Za-z0-9_./-]*\.py)"
    r"(?![\w./-])"
)
TOKEN_PATTERN = re.compile(r"(?<![\w./-])[\w./-]+(?![\w./-])")


def _run_git(repo_root: Path, *args: str) -> str:
    """Return stdout of a git command run at ``repo_root``."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def tracked_files(repo_root: Path, *patterns: str) -> list[str]:
    """Return tracked paths matching ``patterns``, POSIX-normalized."""
    out = _run_git(repo_root, "ls-files", "-z", *patterns)
    return [entry.replace("\\", "/") for entry in out.split("\0") if entry]


def is_in_scope(rel_path: str) -> bool:
    """Return whether a file carries instructions this guard should gate."""
    return not rel_path.startswith(HISTORICAL_ROOTS + GENERATED_ROOTS + FIXTURE_ROOTS)


def is_declared(lines: list[str], index: int) -> bool:
    """Return whether the offense at ``index`` carries a declaration.

    The marker counts on the offending line itself or on the line directly
    above it, so a docstring or a multi-line command block can carry it.
    """
    return any(DECLARATION in lines[i] for i in (index, index - 1) if i >= 0)


def _import_time_nodes(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield statements that execute when the module is imported.

    Descends into ``if``/``try``/``with``/``for`` and class bodies, which run at
    import time. Skips function bodies, whose imports run only when called.
    """
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield node
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(node, field, None)
            if isinstance(nested, list):
                yield from _import_time_nodes(nested)
        for handler in getattr(node, "handlers", []):
            yield from _import_time_nodes(handler.body)


def _imported_roots(tree: ast.Module) -> list[str]:
    """Return top-level module names imported at import time."""
    names: list[str] = []
    for node in _import_time_nodes(tree.body):
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module.split(".")[0])
    return names


def _local_modules(name: str, importer: str, tracked_py: set[str]) -> list[str] | None:
    """Resolve ``import <name>`` from ``importer`` to tracked files.

    Returns the resolved files, or ``None`` when ``name`` is not a repo module.

    Scripts here reach siblings through ``sys.path`` insertion, so a
    same-directory match wins. Failing that, a single repo-wide match is
    unambiguous and is followed. Two or more matches are NOT followed: the guard
    cannot prove which one the runtime loads, and unioning their imports invents
    dependencies. ``scripts/memory/validate_memory_sizes.py`` imports
    ``test_memory_size``, which matches four tracked files; one of them imports
    ``pytest``. Unioning reported the documented command as unportable even
    though ``python3 -S scripts/memory/validate_memory_sizes.py`` succeeds.
    An ambiguous name resolves to "local, nothing proven" so this blocking gate
    fails only on provable cases.
    """
    suffixes = (f"/{name}.py", f"/{name}/__init__.py")
    exact = (f"{name}.py", f"{name}/__init__.py")
    candidates = sorted(p for p in tracked_py if p.endswith(suffixes) or p in exact)
    if not candidates:
        return None
    same_dir = str(Path(importer).parent)
    preferred = [p for p in candidates if str(Path(p).parent) == same_dir]
    if preferred:
        return preferred
    return candidates if len(candidates) == 1 else []


def _tokens_are_uv_run_options(tokens: list[str]) -> bool:
    index = 0
    while index < len(tokens):
        if not tokens[index].startswith("-"):
            return False
        index += 1
        if index < len(tokens) and not tokens[index].startswith("-"):
            index += 1
    return True


def is_uv_run_prefixed(prefix: str) -> bool:
    """Return whether the text before ``python`` is an immediate ``uv run`` prefix."""
    tokens = TOKEN_PATTERN.findall(prefix)
    for index in range(len(tokens) - 2, -1, -1):
        if tokens[index : index + 2] == ["uv", "run"]:
            return _tokens_are_uv_run_options(tokens[index + 2 :])
    return False


def third_party_imports(
    rel_path: str,
    repo_root: Path,
    tracked_py: set[str],
    seen: set[str] | None = None,
) -> set[str]:
    """Return non-stdlib, non-repo modules reachable at import time from ``rel_path``."""
    seen = set() if seen is None else seen
    if rel_path in seen:
        return set()
    seen.add(rel_path)
    try:
        tree = ast.parse((repo_root / rel_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return set()

    found: set[str] = set()
    for name in _imported_roots(tree):
        if name in sys.stdlib_module_names:
            continue
        local = _local_modules(name, rel_path, tracked_py)
        if local is None:
            found.add(name)
            continue
        for target in local:
            found |= third_party_imports(target, repo_root, tracked_py, seen)
    for target in python_subprocess_targets(tree, tracked_py):
        found |= third_party_imports(target, repo_root, tracked_py, seen)
    return found


def find_offenses(line: str, repo_root: Path, tracked_py: set[str]) -> list[tuple[str, list[str]]]:
    """Return (script, third-party modules) for each unportable invocation on ``line``."""
    offenses: list[tuple[str, list[str]]] = []
    for match in INVOCATION_PATTERN.finditer(line):
        if is_uv_run_prefixed(line[: match.start()]):
            continue
        script = match.group("path")
        while script.startswith("./"):
            script = script[2:]
        if script not in tracked_py:
            continue
        external = third_party_imports(script, repo_root, tracked_py)
        if external:
            offenses.append((script, sorted(external)))
    return offenses


def scan(repo_root: Path, details: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Return {file path: sorted script paths} -- identity keys for swap detection (#4292)."""
    tracked_py = set(tracked_files(repo_root, "*.py"))
    counts: dict[str, list[str]] = {}
    for rel in tracked_files(repo_root, "*.md", "*.py"):
        if not is_in_scope(rel):
            continue
        path = repo_root / rel
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        scripts: list[str] = []
        for index, line in enumerate(lines):
            if is_declared(lines, index):
                continue
            offenses = find_offenses(line, repo_root, tracked_py)
            for script, modules in offenses:
                scripts.append(script)
                if details is not None:
                    details.setdefault(rel, []).append(
                        f"{rel}:{index + 1}: {script} imports {', '.join(modules)}"
                    )
        if scripts:
            counts[rel] = sorted(set(scripts))
    return counts


_BaselineValue = list[str] | int


def load_baseline(path: Path) -> dict[str, _BaselineValue]:
    """Load per-file entries as list (identity) or int (legacy count)."""
    if not path.is_file():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    files = data.get("files", data)
    if not isinstance(files, dict):
        raise ValueError("Baseline 'files' must be a JSON object")
    out: dict[str, _BaselineValue] = {}
    for key, value in files.items():
        if isinstance(value, list):
            out[str(key)] = [str(v) for v in value]
        else:
            try:
                out[str(key)] = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Baseline value for {key!r} is not valid") from exc
    return out


def diff_against_baseline(
    current: dict[str, list[str]],
    baseline: dict[str, _BaselineValue],
    details: dict[str, list[str]] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements). List baseline detects swaps (#4292)."""
    regressions: list[str] = []
    for rel, scripts in sorted(current.items()):
        bval = baseline.get(rel)
        extra = f" Offenses: {'; '.join(details.get(rel, []))}" if details else ""
        if isinstance(bval, list):
            new = sorted(set(scripts) - set(bval))
            if new:
                regressions.append(
                    f"{rel}: new invocation(s): {', '.join(new)} (issue #3791).{extra}"
                )
        else:
            allowed = int(bval) if bval is not None else 0
            if len(scripts) > allowed:
                regressions.append(
                    f"{rel}: {len(scripts)} invocation(s) (baseline {allowed}). "
                    f"Use 'uv run python <script>' (issue #3791).{extra}"
                )
    improvements: list[str] = []
    for rel, bval in sorted(baseline.items()):
        cur = len(current.get(rel, []))
        limit = len(bval) if isinstance(bval, list) else int(bval)
        if cur < limit:
            improvements.append(f"{rel}: {cur} invocations (baseline {limit})")
    return regressions, improvements


def validate_doc_interpreter_portability(repo_root: Path) -> bool:
    """Return True when every file is at or below its baseline."""
    return main(["--repo-root", str(repo_root)]) == 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    p = argparse.ArgumentParser(description="Documented-interpreter portability ratchet.")
    p.add_argument("--repo-root", type=Path, default=None)
    p.add_argument("--baseline", type=Path, default=None)
    p.add_argument("--update-baseline", action="store_true")
    return p


def _resolve_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    repo_root = (args.repo_root or Path.cwd()).resolve()
    baseline = args.baseline or repo_root / "scripts" / "validation" / _DEFAULT_BASELINE_NAME
    return repo_root, baseline


def _update_baseline(
    current: dict[str, list[str]],
    baseline_path: Path,
    details: dict[str, list[str]],
) -> int:
    if baseline_path.is_file():
        try:
            previous = load_baseline(baseline_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"check-doc-interpreter-portability: {exc}", file=sys.stderr)
            return 2
        regressions, _ = diff_against_baseline(current, previous, details)
        if regressions:
            for line in regressions:
                print(f"DRIFT {line}", file=sys.stderr)
            print("check-doc-interpreter-portability: refusing to raise baseline", file=sys.stderr)
            return 1
    payload = json.dumps({"files": dict(sorted(current.items()))}, indent=2) + "\n"
    try:
        baseline_path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        print(f"check-doc-interpreter-portability: {exc}", file=sys.stderr)
        return 2
    print(f"check-doc-interpreter-portability: wrote {baseline_path} ({len(current)} files)")
    return 0

def main(argv: list[str] | None = None) -> int:
    """Run the ratchet."""
    args = build_parser().parse_args(argv)
    repo_root, baseline_path = _resolve_roots(args)
    try:
        details: dict[str, list[str]] = {}
        current = scan(repo_root, details)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"check-doc-interpreter-portability: {exc}", file=sys.stderr)
        return 2
    if args.update_baseline:
        return _update_baseline(current, baseline_path, details)
    try:
        baseline = load_baseline(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"check-doc-interpreter-portability: {exc}", file=sys.stderr)
        return 2
    regressions, improvements = diff_against_baseline(current, baseline, details)
    for line in improvements:
        print(f"IMPROVED {line}")
    for line in regressions:
        print(f"DRIFT {line}", file=sys.stderr)
    if regressions:
        print(
            "check-doc-interpreter-portability: FAIL. Rerun with --update-baseline "
            "only after fixing, never to silence a new offender.",
            file=sys.stderr,
        )
        return 1
    print("check-doc-interpreter-portability: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
