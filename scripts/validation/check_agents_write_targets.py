#!/usr/bin/env python3
"""Reject live contracts that write project artifacts below ``.agents/``.

The legacy tree still contains canonical inputs and historical records, so an
occurrence ban would reject valid reads. This check instead recognizes explicit
write prescriptions in text and constant path writes in Python. It scans the
tracked index, including staged content, and deliberately ignores files located
under ``.agents/`` because those are inputs/history classified by issue #5420.

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

_SCANNED_PREFIXES = (".claude/", ".github/", "docs/", "scripts/", "src/", "templates/")
_TEXT_SUFFIXES = (".md", ".txt", ".yml", ".yaml")
_TARGET = re.compile(r"(?<![\w-])\.agents(?:/[^\s`'\"<>),;:]*)?")
_WRITE = re.compile(
    r"\b(?:create|emit|generate|mkdir|output|persist|report|save|store|write)\b",
    re.IGNORECASE,
)
_HISTORICAL = re.compile(r"agents-write-target:\s*historical\s*--\s*\S", re.IGNORECASE)
_WRITE_METHODS = frozenset({"mkdir", "touch", "write_bytes", "write_text"})


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int
    target: str
    reason: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.target}: {self.reason}"


def scan_text(path: str, text: str) -> list[Finding]:
    """Find explicit write verbs and legacy targets in one logical paragraph."""
    findings: list[Finding] = []
    lines = text.splitlines()
    start = 0
    for index in range(len(lines) + 1):
        if index < len(lines) and lines[index].strip():
            continue
        block = "\n".join(lines[start:index])
        if block and not _HISTORICAL.search(block) and _WRITE.search(block):
            for match in _TARGET.finditer(block):
                line = start + block[: match.start()].count("\n") + 1
                findings.append(
                    Finding(path, line, match.group(), "live write contract targets .agents")
                )
        start = index + 1
    return findings


def _constant_path(node: ast.AST) -> str | None:
    """Resolve only literal path expressions; no speculative data flow."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path":
        return _constant_path(node.args[0]) if len(node.args) == 1 else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _constant_path(node.left)
        right = _constant_path(node.right)
        if left is not None and right is not None:
            return f"{left.rstrip('/')}/{right.lstrip('/')}"
        return None
    return None


def _is_legacy(path: str | None) -> bool:
    if path is None:
        return False
    normalized = path.replace("\\", "/").removeprefix("./")
    return normalized == ".agents" or normalized.startswith(".agents/")


def _open_mode(node: ast.Call) -> str:
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        return str(node.args[1].value)
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return "r"


class _PythonWrites(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def _add(self, node: ast.AST, target: str) -> None:
        self.findings.append(
            Finding(self.path, node.lineno, target, "Python write targets .agents")
        )

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _WRITE_METHODS:
            target = _constant_path(func.value)
            if _is_legacy(target):
                self._add(node, target or ".agents")
        elif isinstance(func, ast.Name) and func.id == "open" and node.args:
            target = _constant_path(node.args[0])
            if _is_legacy(target) and any(flag in _open_mode(node) for flag in "wax+"):
                self._add(node, target or ".agents")
        elif isinstance(func, ast.Attribute) and node.args:
            owner = func.value.id if isinstance(func.value, ast.Name) else ""
            if owner == "os" and func.attr in {"mkdir", "makedirs"}:
                target = _constant_path(node.args[0])
                if _is_legacy(target):
                    self._add(node, target or ".agents")
            elif owner == "shutil" and func.attr in {"copy", "copyfile", "copytree", "move"}:
                if len(node.args) > 1:
                    target = _constant_path(node.args[1])
                    if _is_legacy(target):
                        self._add(node, target or ".agents")
        self.generic_visit(node)


def scan_python(path: str, text: str) -> list[Finding]:
    tree = ast.parse(text, filename=path)
    visitor = _PythonWrites(path)
    visitor.visit(tree)
    return visitor.findings


def _tracked_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo_root, capture_output=True,
        encoding="utf-8", errors="replace", check=False, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [path for path in result.stdout.split("\0") if path]


def check_repository(repo_root: Path) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    examined = 0
    for relative in _tracked_files(repo_root):
        if relative.startswith((".agents/", "tests/")) or not relative.startswith(
            _SCANNED_PREFIXES
        ):
            continue
        is_python = relative.endswith(".py")
        if not is_python and not relative.endswith(_TEXT_SUFFIXES):
            continue
        text = (repo_root / relative).read_text(encoding="utf-8", errors="replace")
        examined += 1
        findings.extend(scan_python(relative, text) if is_python else scan_text(relative, text))
    return sorted(findings, key=lambda item: (item.path, item.line, item.target)), examined


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
    parser = argparse.ArgumentParser(description="Reject new writes below .agents/.")
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
