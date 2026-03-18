#!/usr/bin/env python3
"""Documentation Accuracy Scanner - Phases 1-3.

Treats code as the source of truth and documentation as the subject under test.
Produces JSON artifacts for downstream LLM-based verification (Phases 4-6).

Phase 1: Assessment - enumerate docs/source, extract symbols, build mapping
Phase 2: Claim Extraction - parse markdown for verifiable claims
Phase 3: Compilability - verify code example symbols exist in codebase

Exit Codes:
    0: No findings at or above severity threshold
    1: Error (file not found, parse error)
    10: Findings at or above severity threshold
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SourceSymbol:
    """A public symbol extracted from source code."""

    name: str
    kind: str  # class, method, property, constructor, function
    file: str
    line: int
    signature: str
    visibility: str = "public"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "signature": self.signature,
            "visibility": self.visibility,
        }


@dataclass
class DocFile:
    """A documentation file with metadata."""

    path: str
    size_bytes: int
    line_count: int
    code_blocks: int
    referenced_symbols: list[str]
    mapped_source_files: list[str]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "code_blocks": self.code_blocks,
            "referenced_symbols": self.referenced_symbols,
            "mapped_source_files": self.mapped_source_files,
        }


@dataclass
class Claim:
    """A verifiable claim extracted from documentation."""

    id: str
    file: str
    line: int
    claim_type: str  # code_example, method_signature, behavioral, quantitative
    language: str
    content: str
    symbols_referenced: list[str]
    mapped_source: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "line": self.line,
            "type": self.claim_type,
            "language": self.language,
            "content": self.content,
            "symbols_referenced": self.symbols_referenced,
            "mapped_source": self.mapped_source,
        }


@dataclass
class Finding:
    """A compilability or accuracy finding."""

    id: str
    claim_id: str
    severity: str  # critical, high, medium, low
    category: str
    file: str
    line: int
    description: str
    evidence: dict
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "description": self.description,
            "evidence": self.evidence,
            "suggested_fix": self.suggested_fix,
        }


# ---------------------------------------------------------------------------
# Phase 1: Assessment
# ---------------------------------------------------------------------------

# File extensions to language mapping
SOURCE_EXTENSIONS: dict[str, str] = {
    ".cs": "csharp",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}

DOC_GLOBS = ["docs/**/*.md", "**/*.md"]

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    "bin",
    "obj",
    ".doc-accuracy",
}


def _should_exclude(path: Path) -> bool:
    """Check if path is in an excluded directory."""
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def _extract_csharp_symbols(content: str, file_path: str) -> list[SourceSymbol]:
    """Extract public symbols from C# source."""
    symbols: list[SourceSymbol] = []
    lines = content.split("\n")

    pattern = re.compile(
        r"^\s*(?:\[[^\]]*\]\s*)*"
        r"public\s+"
        r"(?:(?:static|virtual|override|abstract|async|sealed|readonly|partial)\s+)*"
        r"(?:(class|struct|interface|enum|record)\s+(\w+)"
        r"|(?:[\w<>\[\],?\s]+)\s+(\w+)\s*[<(])"
    )

    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue

        if match.group(1):
            # Type declaration
            kind = match.group(1)
            name = match.group(2)
            sig = line.strip()
        else:
            # Method or property
            name = match.group(3)
            kind = "method" if "(" in line else "property"
            sig = line.strip()

        symbols.append(SourceSymbol(
            name=name,
            kind=kind,
            file=file_path,
            line=i + 1,
            signature=sig,
        ))

    return symbols


def _extract_python_symbols(content: str, file_path: str) -> list[SourceSymbol]:
    """Extract public symbols from Python source."""
    symbols: list[SourceSymbol] = []
    lines = content.split("\n")
    pattern = re.compile(r"^(\s*)(def|class)\s+(\w+)")

    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue

        kind_token = match.group(2)
        name = match.group(3)

        if name.startswith("_"):
            continue

        kind = "class" if kind_token == "class" else "function"
        symbols.append(SourceSymbol(
            name=name,
            kind=kind,
            file=file_path,
            line=i + 1,
            signature=line.strip(),
        ))

    return symbols


def _extract_js_symbols(content: str, file_path: str) -> list[SourceSymbol]:
    """Extract exported symbols from JavaScript/TypeScript source."""
    symbols: list[SourceSymbol] = []
    lines = content.split("\n")
    pattern = re.compile(
        r"^(?:export\s+)?"
        r"(?:(?:async|default)\s+)*"
        r"(?:function|class|const|let|var|interface|type)\s+"
        r"(\w+)"
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("export"):
            continue

        match = pattern.match(stripped)
        if not match:
            continue

        name = match.group(1)
        kind = "class" if "class " in line else "function"
        symbols.append(SourceSymbol(
            name=name,
            kind=kind,
            file=file_path,
            line=i + 1,
            signature=stripped,
        ))

    return symbols


SYMBOL_EXTRACTORS = {
    "csharp": _extract_csharp_symbols,
    "python": _extract_python_symbols,
    "javascript": _extract_js_symbols,
    "typescript": _extract_js_symbols,
}


def _find_referenced_symbols(
    doc_content: str, symbol_names: set[str]
) -> list[str]:
    """Find source symbols referenced in documentation content."""
    found: list[str] = []
    for name in symbol_names:
        if name in doc_content:
            found.append(name)
    return sorted(set(found))


def _map_doc_to_source(
    doc_path: str,
    doc_content: str,
    source_files: dict[str, str],
) -> list[str]:
    """Map a documentation file to relevant source files."""
    mapped: list[str] = []
    doc_lower = doc_content.lower()

    for src_path in source_files:
        src_name = Path(src_path).stem.lower()
        if src_name in doc_lower:
            mapped.append(src_path)

    return sorted(set(mapped))


def _count_code_blocks(content: str) -> int:
    """Count fenced code blocks in markdown."""
    return len(re.findall(r"^```\w*\s*$", content, re.MULTILINE))


def _get_changed_files(diff_base: str, repo_root: Path) -> set[str]:
    """Get files changed since diff_base."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", diff_base],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
        return {f.strip() for f in result.stdout.strip().split("\n") if f.strip()}
    except subprocess.CalledProcessError:
        return set()


def run_assessment(
    repo_root: Path,
    doc_globs: list[str] | None = None,
    diff_base: str | None = None,
) -> dict:
    """Phase 1: Build assessment of documentation and source files."""
    if doc_globs is None:
        doc_globs = DOC_GLOBS

    changed_files: set[str] | None = None
    if diff_base:
        changed_files = _get_changed_files(diff_base, repo_root)

    # Enumerate documentation files
    doc_files_set: set[Path] = set()
    for glob_pattern in doc_globs:
        for p in repo_root.glob(glob_pattern):
            if p.is_file() and not _should_exclude(p):
                doc_files_set.add(p)

    # Enumerate source files
    source_files: dict[str, str] = {}  # path -> content
    source_symbols: list[SourceSymbol] = []
    symbol_names: set[str] = set()

    for p in repo_root.rglob("*"):
        if not p.is_file() or _should_exclude(p):
            continue

        ext = p.suffix.lower()
        lang = SOURCE_EXTENSIONS.get(ext)
        if not lang:
            continue

        rel_path = str(p.relative_to(repo_root))
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Failed to read source file %s: %s", rel_path, exc)
            continue

        source_files[rel_path] = content

        extractor = SYMBOL_EXTRACTORS.get(lang)
        if extractor:
            syms = extractor(content, rel_path)
            source_symbols.extend(syms)
            for s in syms:
                symbol_names.add(s.name)

    # Build doc file inventory
    doc_inventory: list[DocFile] = []
    for doc_path in sorted(doc_files_set):
        rel_path = str(doc_path.relative_to(repo_root))
        try:
            content = doc_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Failed to read doc file %s: %s", rel_path, exc)
            continue

        refs = _find_referenced_symbols(content, symbol_names)
        mapped = _map_doc_to_source(rel_path, content, source_files)

        doc_inventory.append(DocFile(
            path=rel_path,
            size_bytes=doc_path.stat().st_size,
            line_count=content.count("\n") + 1,
            code_blocks=_count_code_blocks(content),
            referenced_symbols=refs,
            mapped_source_files=mapped,
        ))

    # Build coverage summary
    documented_symbols = set()
    for doc in doc_inventory:
        documented_symbols.update(doc.referenced_symbols)

    public_count = len(source_symbols)
    documented_count = len(documented_symbols & symbol_names)
    coverage_pct = (documented_count / public_count * 100) if public_count else 100.0

    # Find benchmark files
    benchmark_files = []
    for p in repo_root.rglob("*benchmark*"):
        if p.is_file() and not _should_exclude(p):
            benchmark_files.append(str(p.relative_to(repo_root)))
    for p in repo_root.rglob("*bench*"):
        if (
            p.is_file()
            and p.suffix in (".json", ".csv", ".md")
            and not _should_exclude(p)
        ):
            rel = str(p.relative_to(repo_root))
            if rel not in benchmark_files:
                benchmark_files.append(rel)

    return {
        "documentation_files": [d.to_dict() for d in doc_inventory],
        "source_symbols": [s.to_dict() for s in source_symbols],
        "benchmark_files": sorted(benchmark_files),
        "coverage_summary": {
            "public_symbols": public_count,
            "documented_symbols": documented_count,
            "coverage_pct": round(coverage_pct, 1),
        },
        "changed_files": sorted(changed_files) if changed_files else None,
    }


# ---------------------------------------------------------------------------
# Phase 2: Claim Extraction
# ---------------------------------------------------------------------------

def _detect_language(info_string: str) -> str:
    """Detect language from code fence info string."""
    lang_map = {
        "csharp": "csharp",
        "cs": "csharp",
        "c#": "csharp",
        "python": "python",
        "py": "python",
        "javascript": "javascript",
        "js": "javascript",
        "typescript": "typescript",
        "ts": "typescript",
        "bash": "bash",
        "sh": "bash",
        "shell": "bash",
        "powershell": "powershell",
        "ps1": "powershell",
        "pwsh": "powershell",
        "yaml": "yaml",
        "yml": "yaml",
        "json": "json",
        "xml": "xml",
        "go": "go",
        "rust": "rust",
        "rs": "rust",
        "java": "java",
    }
    token = info_string.strip().lower().split()[0] if info_string.strip() else ""
    return lang_map.get(token, token)


def _extract_identifiers(code: str) -> list[str]:
    """Extract potential identifiers from a code snippet."""
    # Match CamelCase and snake_case identifiers (3+ chars)
    identifiers = re.findall(r"\b([A-Z][a-zA-Z0-9]+)\b", code)
    # Also match method calls
    identifiers.extend(re.findall(r"\.([A-Za-z]\w+)\s*\(", code))
    # Named parameters (C# style)
    identifiers.extend(re.findall(r"(\w+)\s*:", code))
    return sorted(set(identifiers))


def _extract_quantitative_claims(line: str) -> list[str]:
    """Find quantitative claims in a line of text."""
    patterns = [
        r"[<>~]\s*\d+[%]",           # <5%, >90%, ~10%
        r"\d+-\d+\s*(?:ns|ms|us|s)\b",  # 15-40ns
        r"\d+\s*(?:ns|ms|us|s)\b",    # 100ns
        r"\d+(?:\.\d+)?%",            # 33.4%
        r"\+\d+(?:\.\d+)?%",          # +93.1%
    ]
    claims = []
    for p in patterns:
        claims.extend(re.findall(p, line))
    return claims


def run_claim_extraction(
    repo_root: Path,
    assessment: dict,
) -> dict:
    """Phase 2: Extract verifiable claims from documentation files."""
    claims: list[Claim] = []
    claim_counter = 0

    # Build symbol -> source file mapping
    symbol_to_source: dict[str, str] = {}
    for sym in assessment.get("source_symbols", []):
        symbol_to_source[sym["name"]] = sym["file"]

    for doc_info in assessment.get("documentation_files", []):
        doc_path = repo_root / doc_info["path"]
        try:
            content = doc_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning(
                "Failed to read doc file %s: %s", doc_info["path"], exc
            )
            continue

        lines = content.split("\n")
        mapped_sources = doc_info.get("mapped_source_files", [])
        default_source = mapped_sources[0] if mapped_sources else ""

        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect fenced code blocks
            fence_match = re.match(r"^```(\w*)", line)
            if fence_match:
                lang = _detect_language(fence_match.group(1))
                block_start = i + 1
                i += 1
                block_lines = []
                while i < len(lines) and not lines[i].startswith("```"):
                    block_lines.append(lines[i])
                    i += 1

                code_content = "\n".join(block_lines)
                if not code_content.strip():
                    i += 1
                    continue

                identifiers = _extract_identifiers(code_content)
                # Map identifiers to source files
                mapped = default_source
                for ident in identifiers:
                    if ident in symbol_to_source:
                        mapped = symbol_to_source[ident]
                        break

                claim_counter += 1
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=block_start,
                    claim_type="code_example",
                    language=lang,
                    content=code_content,
                    symbols_referenced=identifiers,
                    mapped_source=mapped,
                ))
                i += 1
                continue

            # Detect behavioral claims (sentences with method references)
            method_ref = re.search(
                r"`(\w+)\(\)`\s+(?:emits?|returns?|throws?|creates?|produces?)",
                line,
            )
            if method_ref:
                claim_counter += 1
                method_name = method_ref.group(1)
                mapped = symbol_to_source.get(method_name, default_source)
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=i + 1,
                    claim_type="behavioral",
                    language="",
                    content=line.strip(),
                    symbols_referenced=[method_name],
                    mapped_source=mapped,
                ))

            # Detect quantitative claims
            quant_claims = _extract_quantitative_claims(line)
            if quant_claims:
                claim_counter += 1
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=i + 1,
                    claim_type="quantitative",
                    language="",
                    content=line.strip(),
                    symbols_referenced=quant_claims,
                    mapped_source=default_source,
                ))

            # Detect method signature claims
            sig_match = re.search(
                r"(?:constructor|method|function)\s+(?:accepts?|takes?|requires?)\s+"
                r"`([^`]+)`",
                line,
                re.IGNORECASE,
            )
            if sig_match:
                claim_counter += 1
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=i + 1,
                    claim_type="method_signature",
                    language="",
                    content=line.strip(),
                    symbols_referenced=_extract_identifiers(sig_match.group(1)),
                    mapped_source=default_source,
                ))

            i += 1

    return {"claims": [c.to_dict() for c in claims]}


# ---------------------------------------------------------------------------
# Phase 3: Compilability Check
# ---------------------------------------------------------------------------

def run_compilability_check(
    assessment: dict,
    claims_data: dict,
) -> dict:
    """Phase 3: Verify symbols in code examples exist in the codebase."""
    findings: list[Finding] = []
    finding_counter = 0

    # Build symbol index from assessment
    symbol_index: dict[str, SourceSymbol] = {}
    for sym_dict in assessment.get("source_symbols", []):
        sym = SourceSymbol(**sym_dict)
        symbol_index[sym.name] = sym

    # Build a set of all known symbol names for quick lookup
    known_names = set(symbol_index.keys())

    for claim_dict in claims_data.get("claims", []):
        if claim_dict["type"] not in ("code_example", "method_signature"):
            continue

        content = claim_dict["content"]
        lang = claim_dict.get("language", "")

        # Skip non-code languages
        if lang in ("bash", "shell", "yaml", "yml", "json", "xml", "markdown", ""):
            if claim_dict["type"] == "code_example":
                continue

        symbols_ref = claim_dict.get("symbols_referenced", [])
        if not symbols_ref:
            continue

        for sym_name in symbols_ref:
            if sym_name in known_names:
                # Symbol exists, check for parameter accuracy
                actual = symbol_index[sym_name]
                if actual.kind == "method" and "(" in content:
                    # Check named parameters in the code example
                    named_params = re.findall(
                        rf"{re.escape(sym_name)}\s*\([^)]*?(\w+)\s*:",
                        content,
                    )
                    for param in named_params:
                        if param not in actual.signature:
                            finding_counter += 1
                            findings.append(Finding(
                                id=f"compile-{finding_counter:04d}",
                                claim_id=claim_dict["id"],
                                severity="critical",
                                category="phantom_parameter",
                                file=claim_dict["file"],
                                line=claim_dict["line"],
                                description=(
                                    f"Parameter '{param}' does not exist in "
                                    f"{sym_name}(). "
                                    f"Actual signature: {actual.signature}"
                                ),
                                evidence={
                                    "documented": content[:200],
                                    "actual_signature": actual.signature,
                                    "source_file": actual.file,
                                    "source_line": actual.line,
                                },
                                suggested_fix=(
                                    f"Remove or rename parameter '{param}'. "
                                    f"Check {actual.file}:{actual.line} for "
                                    f"correct signature."
                                ),
                            ))
            else:
                # Symbol not found in codebase
                # Only flag CamelCase identifiers (likely type/method names)
                if not re.match(r"^[A-Z][a-zA-Z0-9]+$", sym_name):
                    continue

                # Skip common framework types
                framework_types = {
                    "String", "Int32", "Boolean", "Object", "Array",
                    "List", "Dictionary", "Task", "Action", "Func",
                    "IEnumerable", "IList", "Console", "Exception",
                    "Math", "DateTime", "TimeSpan", "Path", "File",
                    "Directory", "Type", "Attribute", "Nullable",
                    "True", "False", "None", "Error", "Promise",
                }
                if sym_name in framework_types:
                    continue

                finding_counter += 1
                findings.append(Finding(
                    id=f"compile-{finding_counter:04d}",
                    claim_id=claim_dict["id"],
                    severity="high",
                    category="unresolved_symbol",
                    file=claim_dict["file"],
                    line=claim_dict["line"],
                    description=(
                        f"Symbol '{sym_name}' referenced in documentation "
                        f"not found in codebase"
                    ),
                    evidence={
                        "documented": content[:200],
                        "symbol": sym_name,
                        "search_scope": "all source files",
                    },
                    suggested_fix=(
                        f"Verify '{sym_name}' exists in the codebase. "
                        f"It may be misspelled, renamed, or removed."
                    ),
                ))

    return {"findings": [f.to_dict() for f in findings]}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def check_gate(
    compilability_data: dict | None,
    severity_threshold: str,
) -> dict:
    """Evaluate findings against severity threshold.

    Returns a gate_result dict with verdict and counts.
    """
    threshold_level = SEVERITY_ORDER.get(severity_threshold, 1)
    by_severity: dict[str, int] = {}
    blocking_count = 0

    if compilability_data:
        for finding in compilability_data["findings"]:
            sev = finding["severity"]
            by_severity[sev] = by_severity.get(sev, 0) + 1
            finding_level = SEVERITY_ORDER.get(sev, 3)
            if finding_level <= threshold_level:
                blocking_count += 1

    verdict = "FAIL" if blocking_count > 0 else "PASS"
    return {
        "verdict": verdict,
        "threshold": severity_threshold,
        "blocking_findings": blocking_count,
        "total_findings": sum(by_severity.values()),
        "by_severity": by_severity,
    }


def generate_markdown_report(
    assessment: dict | None,
    claims_data: dict | None,
    compilability_data: dict | None,
    gate_result: dict,
    output_path: Path,
) -> None:
    """Write a markdown summary report to output_path."""
    lines: list[str] = []
    lines.append("# Documentation Accuracy Report")
    lines.append("")

    lines.append(
        f"**Gate: {gate_result['verdict']}** "
        f"(threshold: {gate_result['threshold']})"
    )
    lines.append("")

    if assessment:
        cs = assessment["coverage_summary"]
        lines.append("## Coverage")
        lines.append("")
        lines.append(f"- Public symbols: {cs['public_symbols']}")
        lines.append(f"- Documented symbols: {cs['documented_symbols']}")
        lines.append(f"- Coverage: {cs['coverage_pct']}%")
        lines.append("")

    if claims_data:
        by_type: dict[str, int] = {}
        for c in claims_data["claims"]:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        lines.append("## Claims")
        lines.append("")
        lines.append(f"Total: {len(claims_data['claims'])}")
        lines.append("")
        for ct, count in sorted(by_type.items()):
            lines.append(f"- {ct}: {count}")
        lines.append("")

    if compilability_data and compilability_data["findings"]:
        lines.append("## Findings")
        lines.append("")
        lines.append(
            f"Total: {gate_result['total_findings']} "
            f"({gate_result['blocking_findings']} blocking)"
        )
        lines.append("")
        lines.append("| Severity | File | Line | Description |")
        lines.append("|----------|------|------|-------------|")
        for f in compilability_data["findings"]:
            desc = f["description"][:80]
            lines.append(
                f"| {f['severity']} | {f['file']} | {f['line']} | {desc} |"
            )
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _print_summary(
    assessment: dict | None,
    claims_data: dict | None,
    compilability_data: dict | None,
    gate_result: dict,
) -> None:
    """Print a text summary to stdout."""
    print("\n--- Documentation Accuracy Summary ---")
    if assessment:
        cs = assessment["coverage_summary"]
        print(
            f"Symbols: {cs['documented_symbols']}/{cs['public_symbols']} "
            f"({cs['coverage_pct']}% coverage)"
        )
    if claims_data:
        by_type: dict[str, int] = {}
        for c in claims_data["claims"]:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        print(f"Claims: {len(claims_data['claims'])} total")
        for ct, count in sorted(by_type.items()):
            print(f"  {ct}: {count}")
    if compilability_data:
        print(f"Findings: {gate_result['total_findings']} total")
        for sev in ("critical", "high", "medium", "low"):
            count = gate_result["by_severity"].get(sev, 0)
            if count:
                print(f"  {sev}: {count}")
    print(
        f"Gate: {gate_result['verdict']} "
        f"(threshold: {gate_result['threshold']})"
    )


def _load_json_artifact(path: Path, name: str) -> dict | None:
    """Load a JSON artifact file, returning None with error on failure."""
    if not path.exists():
        print(
            f"ERROR: {name} not found. Run the required phase first.",
            file=sys.stderr,
        )
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Documentation accuracy scanner (Phases 1-3)"
    )
    parser.add_argument(
        "--target", "-t", type=Path, required=True,
        help="Repository root to scan",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=None,
        help="Output directory for JSON artifacts "
        "(default: <target>/.doc-accuracy)",
    )
    parser.add_argument(
        "--phases", type=str, default="1,2,3",
        help="Comma-separated phases to run (default: 1,2,3)",
    )
    parser.add_argument(
        "--diff-base", type=str, default=None,
        help="Git ref for incremental mode (only report changed files)",
    )
    parser.add_argument(
        "--severity-threshold", type=str, default="high",
        choices=["critical", "high", "medium", "low"],
        help="Minimum severity for non-zero exit code (default: high)",
    )
    parser.add_argument(
        "--format", "-f", type=str, default="json",
        choices=["json", "summary", "markdown"],
        help="Output format (default: json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for doc-accuracy scanner."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Validate target path (CWE-22 prevention)
    target = args.target.resolve()
    if not target.is_dir():
        print(f"ERROR: Target is not a directory: {target}", file=sys.stderr)
        return 1

    # Set up output directory
    output_dir = args.output_dir or (target / ".doc-accuracy")
    output_dir = output_dir.resolve()

    # Validate output_dir is within or adjacent to target
    try:
        output_dir.relative_to(target)
    except ValueError:
        if args.output_dir is None:
            print(
                f"ERROR: Output directory outside target: {output_dir}",
                file=sys.stderr,
            )
            return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    phases = {int(p.strip()) for p in args.phases.split(",")}

    assessment = None
    claims_data = None
    compilability_data = None

    # Phase 1: Assessment
    if 1 in phases or 2 in phases or 3 in phases:
        print("Phase 1: Assessment...", file=sys.stderr)
        assessment = run_assessment(target, diff_base=args.diff_base)
        (output_dir / "assessment.json").write_text(
            json.dumps(assessment, indent=2), encoding="utf-8"
        )
        doc_count = len(assessment["documentation_files"])
        sym_count = len(assessment["source_symbols"])
        print(
            f"  Found {doc_count} doc files, {sym_count} source symbols",
            file=sys.stderr,
        )

    # Phase 2: Claim Extraction
    if 2 in phases or 3 in phases:
        if assessment is None:
            assessment = _load_json_artifact(
                output_dir / "assessment.json", "assessment.json"
            )
            if assessment is None:
                return 1

        print("Phase 2: Claim Extraction...", file=sys.stderr)
        claims_data = run_claim_extraction(target, assessment)
        (output_dir / "claims.json").write_text(
            json.dumps(claims_data, indent=2), encoding="utf-8"
        )
        print(
            f"  Extracted {len(claims_data['claims'])} claims",
            file=sys.stderr,
        )

    # Phase 3: Compilability Check
    if 3 in phases:
        if assessment is None:
            assessment = _load_json_artifact(
                output_dir / "assessment.json", "assessment.json"
            )
            if assessment is None:
                return 1

        if claims_data is None:
            claims_data = _load_json_artifact(
                output_dir / "claims.json", "claims.json"
            )
            if claims_data is None:
                return 1

        print("Phase 3: Compilability Check...", file=sys.stderr)
        compilability_data = run_compilability_check(assessment, claims_data)
        (output_dir / "compilability-findings.json").write_text(
            json.dumps(compilability_data, indent=2), encoding="utf-8"
        )
        finding_count = len(compilability_data["findings"])
        print(
            f"  Found {finding_count} compilability issues",
            file=sys.stderr,
        )

    # Gate evaluation
    gate_result = check_gate(compilability_data, args.severity_threshold)

    # Write gate result
    (output_dir / "gate-result.json").write_text(
        json.dumps(gate_result, indent=2), encoding="utf-8"
    )

    # Output report
    if args.format == "summary":
        _print_summary(
            assessment, claims_data, compilability_data, gate_result
        )
    elif args.format == "markdown":
        report_path = output_dir / "report.md"
        generate_markdown_report(
            assessment, claims_data, compilability_data,
            gate_result, report_path,
        )
        print(f"Report written to {report_path}", file=sys.stderr)

    if gate_result["verdict"] == "FAIL":
        return 10

    return 0


if __name__ == "__main__":
    sys.exit(main())
