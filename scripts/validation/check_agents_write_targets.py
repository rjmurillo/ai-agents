#!/usr/bin/env python3
"""Reject stale ``.agents/<sub>`` references and writes below ``.agents/``.

Issue #5420 moved every agent write target from ``.agents/<sub>`` to
``.project-toolkit/<sub>``. ``.agents/`` keeps only read-only inputs: the KEEP
subtrees below and its top-level files. Two independent findings:

  (a) STALE ROOT: ``.agents/<sub>`` with ``<sub>`` outside KEEP, read or
      write, in slash, backslash, or Python join form. Globs and regexes are
      patterns, not paths, and are skipped.
  (b) WRITE INTO KEEP / BARE ROOT: a write verb governing the path, a shell
      redirect or ``tee``, a shell or env assignment, or a Python write call
      aimed at a KEEP subtree, a top-level file, or the bare root.

Content comes from the git INDEX (``git ls-files -s``, then one
``git cat-file --batch``), so a staged edit is what gets checked.

Scope: ``.claude/ .github/ build/ docs/ scripts/ src/ templates/ tests/`` and
repo-root ``*.md``. ``tests/`` is scanned because a fixture can teach an agent
a stale path; Python literals under ``tests/`` are fixture data, so only their
AST writes are checked. Never scanned: history (``.project-toolkit/**``,
``.agents/archive/**``, ``.claude-mem/**``), eval scenario data
(``tests/evals/``, which describes consumer repositories), and this module and
its tests. A line opts out with ``agents-write-target: historical -- <reason>``.

Exit codes follow ADR-035: 0 clean, 1 findings, 2 configuration error.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_KEEP_DIRS = frozenset(
    {
        "governance",
        "steering",
        "context",
        "schemas",
        "templates",
        "dictionaries",
        "guides",
        "hooks",
        "skills",
        "archive",
    }
)

_SCANNED_PREFIXES = (
    ".claude/",
    ".github/",
    "build/",
    "docs/",
    "scripts/",
    "src/",
    "templates/",
    "tests/",
)
_EXCLUDED_PREFIXES = (".project-toolkit/", ".agents/archive/", ".claude-mem/")
_EVAL_DATA_PREFIX = "tests/evals/"
_UNSCANNED_PREFIXES = (*_EXCLUDED_PREFIXES, _EVAL_DATA_PREFIX)
_SELF_TEST = "tests/validation/test_check_agents_write_targets.py"
_SELF_SOURCE = "scripts/validation/check_agents_write_targets.py"
_TEST_PREFIX = "tests/"
_TEXT_SUFFIXES = (".md", ".txt", ".yml", ".yaml", ".ps1", ".psm1", ".sh", ".json", ".toml")

_STALE_REASON = "path no longer exists; use .project-toolkit/<sub>"
_TEXT_WRITE_REASON = "live write contract targets .agents"
_PYTHON_WRITE_REASON = "Python write targets .agents"
_MARKER_MISSING_REASON = "agents-write-target: historical marker requires a non-empty reason"

_TARGET = re.compile(r"(?<![\w.-])\.agents(?:[/\\][^\s`'\"<>),;:]*)?")
# No "output" or "report": both read as nouns far more often than as verbs.
_WRITE = re.compile(
    r"\b(?:append|create|edit|emit|generate|mkdir|overwrite|persist|save|store|write)\b",
    re.IGNORECASE,
)
# Between a write verb and the path, these mean the path is only read or cited.
_GAP_READ = re.compile(
    r"\b(?:against|conform\w*|from|match\w*|per|see|using|via|read\w*|load\w*|cites?)\b",
    re.IGNORECASE,
)
_OTHER_PATH = re.compile(r"[\w.-]+/[\w./*{}-]*")
_MAX_GAP_WORDS = 6
# A segment carrying glob or regex syntax is a pattern, not a directory name.
_PATTERN_CHARS = frozenset("*?[]{}()^$|+")
_REDIRECT = re.compile(r"(?:>{1,2}|\btee\b)\s*[`'\"]?$")
_ASSIGN = re.compile(
    r"(?:export\s+)?[A-Za-z_]\w*\s*=\s*[\"']?$|\$env:[A-Za-z_]\w*\s*=\s*[\"']?$"
)
_READ_CONTEXT = re.compile(
    r"(?:from (?:the )?template at|inventory:|per|see|via)\s*[`'\"]?$",
    re.IGNORECASE,
)
_MARKER_WITH_REASON = re.compile(r"agents-write-target:\s*historical\s*--\s*\S")
_MARKER_BARE = re.compile(r"agents-write-target:\s*historical\b")
_WRITE_METHODS = frozenset({"mkdir", "touch", "write_bytes", "write_text"})


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int
    target: str
    reason: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.target}: {self.reason}"


def _agents_kind(match_text: str) -> str:
    """Classify a matched ``.agents`` reference as stale, keep, bare, or pattern.

    ``pattern`` covers globs and regexes such as ``.agents/**`` and prose such
    as ``.agents/-class``: neither names a directory that could have moved.
    """
    normalized = match_text.replace("\\", "/")
    rest = normalized[len(".agents") :].lstrip("/")
    if not rest:
        return "bare"
    segment = rest.split("/", 1)[0]
    if not segment[:1].isalnum() or _PATTERN_CHARS.intersection(segment):
        return "pattern"
    if "/" not in rest and "." in segment:
        return "keep"  # a bare top-level file reference, e.g. .agents/HANDOFF.md
    return "keep" if segment in _KEEP_DIRS else "stale"


def _targets_agents(path: str | None) -> bool:
    if path is None:
        return False
    normalized = path.replace("\\", "/").removeprefix("./")
    return normalized == ".agents" or normalized.startswith(".agents/")


def _has_write_intent(prefix: str) -> bool:
    """Detect a write verb, shell redirect, or assignment just before a match."""
    if _REDIRECT.search(prefix) or _ASSIGN.search(prefix):
        return True
    verbs = list(_WRITE.finditer(prefix))
    if not verbs or _READ_CONTEXT.search(prefix):
        return False
    return _is_direct_object_gap(prefix[verbs[-1].end() :])


def _is_direct_object_gap(gap: str) -> bool:
    """True when the text after a write verb leads straight to the path.

    "Save the report to `.agents/x`" qualifies. A gap that names another path,
    uses a read preposition ("from", "against", "matching"), or runs longer
    than a short noun phrase means the verb governs something else.
    """
    if _TARGET.search(gap) or _OTHER_PATH.search(gap) or _GAP_READ.search(gap):
        return False
    return len(re.findall(r"[A-Za-z]+", gap)) <= _MAX_GAP_WORDS


def scan_text(path: str, text: str) -> list[Finding]:
    """Flag stale-subtree references and write intent aimed at .agents/."""
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if _MARKER_WITH_REASON.search(line):
            continue
        if _MARKER_BARE.search(line):
            findings.append(
                Finding(path, line_number, "agents-write-target", _MARKER_MISSING_REASON)
            )
            continue
        findings.extend(_scan_line(path, line_number, line))
    return findings


def _scan_line(path: str, line_number: int, line: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in _TARGET.finditer(line):
        kind = _agents_kind(match.group())
        if kind == "pattern":
            continue
        if kind == "stale":
            findings.append(Finding(path, line_number, match.group(), _STALE_REASON))
        elif _has_write_intent(line[: match.start()]):
            findings.append(Finding(path, line_number, match.group(), _TEXT_WRITE_REASON))
    return findings


def _constant_path(node: ast.AST, variables: dict[str, str] | None = None) -> str | None:
    """Resolve literal path expressions and single-assignment local variables."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return (variables or {}).get(node.id)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path":
        return _constant_path(node.args[0], variables) if len(node.args) == 1 else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _constant_path(node.left, variables)
        right = _constant_path(node.right, variables)
        if left is not None and right is not None:
            return f"{left.rstrip('/')}/{right.lstrip('/')}"
        return None
    return None


def _find_agents_join(parts: list[ast.expr]) -> str | None:
    """Find a literal ``.agents`` immediately followed by a literal segment."""
    for left, right in zip(parts, parts[1:], strict=False):
        if (
            isinstance(left, ast.Constant)
            and left.value == ".agents"
            and isinstance(right, ast.Constant)
            and isinstance(right.value, str)
        ):
            return f".agents/{right.value}"
    return None


def _resolve_agents_reference(node: ast.AST, variables: dict[str, str]) -> str | None:
    """Resolve BinOp/Path chains, ``os.path.join`` calls, and tuple/list joins."""
    direct = _constant_path(node, variables)
    if direct is not None:
        return direct
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "join":
            return _find_agents_join(list(node.args))
    if isinstance(node, (ast.Tuple, ast.List)):
        return _find_agents_join(list(node.elts))
    return None


def _single_assigned_paths(tree: ast.AST) -> dict[str, str]:
    """Map names assigned exactly once to a literal ``.agents`` path."""
    counts: dict[str, int] = {}
    resolved: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        counts[target.id] = counts.get(target.id, 0) + 1
        value = _constant_path(node.value)
        if value is not None and _targets_agents(value):
            resolved[target.id] = value
    return {name: path for name, path in resolved.items() if counts[name] == 1}


class _PythonAgentsScan(ast.NodeVisitor):
    """Find stale-subtree references and writes aimed at .agents/ in Python."""

    def __init__(self, path: str, variables: dict[str, str]) -> None:
        self.path = path
        self.variables = variables
        self.findings: list[Finding] = []

    def _flag_stale(self, node: ast.AST, target: str) -> bool:
        if _targets_agents(target) and _agents_kind(target) == "stale":
            line = getattr(node, "lineno", 0)
            self.findings.append(Finding(self.path, line, target, _STALE_REASON))
            return True
        return False

    def _flag_write(self, node: ast.AST, target: str | None) -> None:
        if target and _targets_agents(target) and _agents_kind(target) != "stale":
            self.findings.append(
                Finding(self.path, getattr(node, "lineno", 0), target, _PYTHON_WRITE_REASON)
            )

    def visit_BinOp(self, node: ast.BinOp) -> None:
        target = _resolve_agents_reference(node, self.variables)
        if target and self._flag_stale(node, target):
            return
        self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self._visit_join_literal(node)

    def visit_List(self, node: ast.List) -> None:
        self._visit_join_literal(node)

    def _visit_join_literal(self, node: ast.Tuple | ast.List) -> None:
        target = _resolve_agents_reference(node, self.variables)
        if target and self._flag_stale(node, target):
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = _resolve_agents_reference(node, self.variables)
        if target and self._flag_stale(node, target):
            return
        func = node.func
        if isinstance(func, ast.Attribute):
            self._visit_attribute_call(node, func)
        elif isinstance(func, ast.Name) and func.id == "open" and node.args:
            if any(flag in _open_mode(node) for flag in "wax+"):
                self._flag_write(node, _constant_path(node.args[0], self.variables))
        self.generic_visit(node)

    def _visit_attribute_call(self, node: ast.Call, func: ast.Attribute) -> None:
        if func.attr in _WRITE_METHODS:
            self._flag_write(node, _constant_path(func.value, self.variables))
            return
        if func.attr == "open":
            if any(flag in _path_open_mode(node) for flag in "wax+"):
                self._flag_write(node, _constant_path(func.value, self.variables))
            return
        if node.args:
            self._visit_module_write(node, func)

    def _visit_module_write(self, node: ast.Call, func: ast.Attribute) -> None:
        owner = func.value.id if isinstance(func.value, ast.Name) else ""
        if owner == "os" and func.attr in {"mkdir", "makedirs"}:
            self._flag_write(node, _constant_path(node.args[0], self.variables))
        elif owner == "shutil" and func.attr in {"copy", "copyfile", "copytree", "move"}:
            if len(node.args) > 1:
                self._flag_write(node, _constant_path(node.args[1], self.variables))


def _open_mode(node: ast.Call) -> str:
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        return str(node.args[1].value)
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return "r"


def _path_open_mode(node: ast.Call) -> str:
    if node.args and isinstance(node.args[0], ast.Constant):
        return str(node.args[0].value)
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return "r"


def scan_python(path: str, text: str) -> list[Finding]:
    """AST writes and joins, plus stale slash-form paths in strings and comments.

    The per-line stale scan catches a literal such as ``".agents/sessions/x"``
    that no join or write call wraps. It is skipped under ``tests/``, where such
    literals are fixture data. The opt-out marker works per line here the same
    way it does for text files.
    """
    tree = ast.parse(text, filename=path)
    variables = _single_assigned_paths(tree)
    visitor = _PythonAgentsScan(path, variables)
    visitor.visit(tree)
    lines = text.splitlines()
    unique = {(item.line, item.reason): item for item in visitor.findings}
    literal_findings = [] if path.startswith(_TEST_PREFIX) else _stale_line_findings(path, lines)
    for item in literal_findings:
        unique.setdefault((item.line, item.reason), item)
    return [item for item in unique.values() if not _line_opted_out(lines, item.line)]


def _stale_line_findings(path: str, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(lines, 1):
        if _MARKER_BARE.search(line) and not _MARKER_WITH_REASON.search(line):
            findings.append(
                Finding(path, line_number, "agents-write-target", _MARKER_MISSING_REASON)
            )
            continue
        for match in _TARGET.finditer(line):
            if _agents_kind(match.group()) == "stale":
                findings.append(Finding(path, line_number, match.group(), _STALE_REASON))
    return findings


def _line_opted_out(lines: list[str], line_number: int) -> bool:
    if not 0 < line_number <= len(lines):
        return False
    return _MARKER_WITH_REASON.search(lines[line_number - 1]) is not None


def _git(repo_root: Path, args: list[str], stdin: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        input=stdin,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {args[0]} failed: {detail}")
    return result.stdout


def _tracked_files(repo_root: Path) -> dict[str, str]:
    """Map each regular tracked file to its staged blob id (``git ls-files -s``)."""
    result = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    listing = result.stdout
    blobs: dict[str, str] = {}
    for record in listing.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        mode, blob, _stage = meta.split(" ")
        if mode.startswith("100"):
            blobs[path] = blob
    return blobs


def _read_blobs(repo_root: Path, blob_ids: list[str]) -> dict[str, str]:
    """Read staged blob content in one ``git cat-file --batch`` call.

    One process instead of one ``git show`` per file: the per-file form took
    about a minute on this repository, too slow for a pre-commit hook.
    """
    if not blob_ids:
        return {}
    unique = list(dict.fromkeys(blob_ids))
    output = _git(repo_root, ["cat-file", "--batch"], "\n".join(unique).encode() + b"\n")
    contents: dict[str, str] = {}
    offset = 0
    for blob in unique:
        header_end = output.index(b"\n", offset)
        size = int(output[offset:header_end].split(b" ")[2])
        body = output[header_end + 1 : header_end + 1 + size]
        contents[blob] = body.decode("utf-8", errors="replace")
        offset = header_end + 1 + size + 1
    return contents


def _is_candidate(relative: str) -> bool:
    return _is_scanned(relative) and relative.endswith((".py", *_TEXT_SUFFIXES))


def _is_scanned(relative: str) -> bool:
    if relative in (_SELF_TEST, _SELF_SOURCE) or relative.startswith(_UNSCANNED_PREFIXES):
        return False
    if relative.startswith(_SCANNED_PREFIXES):
        return True
    return "/" not in relative and relative.endswith(".md")


def check_repository(repo_root: Path) -> tuple[list[Finding], int]:
    candidates = {
        relative: blob
        for relative, blob in _tracked_files(repo_root).items()
        if _is_candidate(relative)
    }
    contents = _read_blobs(repo_root, list(candidates.values()))
    findings: list[Finding] = []
    for relative, blob in candidates.items():
        text = contents[blob]
        scan = scan_python if relative.endswith(".py") else scan_text
        findings.extend(scan(relative, text))
    return sorted(findings, key=lambda item: (item.path, item.line, item.target)), len(candidates)


def validate_agents_write_targets(repo_root: Path) -> bool:
    try:
        findings, examined = check_repository(repo_root)
    except (OSError, RuntimeError, SyntaxError) as error:
        print(f"[FAIL] legacy .agents write targets: {error}", file=sys.stderr)
        return False
    for finding in findings:
        print(f"  {finding.render()}")
    print(f"agents-write-targets: {len(findings)} violation(s) in {examined} examined files")
    return not findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject stale/write references below .agents/.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    if not (root / ".git").exists():
        print(f"error: not a git repository: {root}", file=sys.stderr)
        return 2
    try:
        findings, examined = check_repository(root)
    except (OSError, RuntimeError, SyntaxError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding.render())
    print(f"agents-write-targets: {len(findings)} violation(s) in {examined} examined files")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
