"""The `draft` subcommand of adr_drift.py: one ADR draft from one scan finding.

Stdlib only. No model: the draft restates the commit (or PR) text and links to it.

Writes one new file and nothing else. The file is opened with mode "x", so an
existing target is never replaced. Inside the repository the target folder must
be one of the folders `locate` reports.

The folder convention (prefix, zero padding, H1 form, section headings, and
frontmatter keys) comes from `adr_corpus.folder_style`, which follows the newest
record in the target folder, then in the repository.

Heading names and H1 forms follow the catalog in the adr-generator skill's
`references/adr-templates-catalog.md`: the canonical set (Status, Context,
Decision, Consequences) and the MADR set (Context and Problem Statement,
Decision Outcome).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adr_corpus import AdrDir, FolderStyle, find_adr_dirs, folder_style, load_dir, within

NOT_RECORDED = "Not recorded in the source."
DRAFTABLE_KINDS = frozenset({"undocumented-decision"})
SLUG_MAX = 60
CONVENTIONAL_PREFIX = re.compile(r"^\w+(?:\([^)]*\))?!?:\s*")
TRAILING_PR = re.compile(r"\s*\(#\d+\)\s*$")
CONTEXT_HEADINGS = frozenset({"context", "context and problem statement"})
DECISION_HEADINGS = frozenset({"decision", "decision outcome"})
REFERENCE_HEADINGS = frozenset({"references", "more information"})


class DraftError(Exception):
    """A draft could not be written. `code` is the exit code (1 or 2)."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Source:
    title: str
    decision: str
    context: str
    date: str
    links: list[str]


def load_finding(scan_file: str, finding_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        scan = json.loads(Path(scan_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DraftError(2, f"cannot read scan file {scan_file}: {exc}") from exc
    findings = scan.get("findings") if isinstance(scan, dict) else None
    if not isinstance(findings, list) or not isinstance(scan.get("repo"), str):
        raise DraftError(2, f"{scan_file} is not an adr_drift scan result")
    for finding in findings:
        if isinstance(finding, dict) and finding.get("id") == finding_id:
            if finding.get("kind") not in DRAFTABLE_KINDS:
                raise DraftError(
                    2, f"finding {finding_id} is a {finding.get('kind')}, not draftable"
                )
            return scan, finding
    raise DraftError(2, f"no finding with id {finding_id} in {scan_file}")


def clean_title(subject: str) -> str:
    title = TRAILING_PR.sub("", CONVENTIONAL_PREFIX.sub("", subject.strip())).strip()
    return (title[:1].upper() + title[1:]) if title else "Untitled decision"


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:SLUG_MAX].rstrip("-")
    return slug or "decision"


def source_from(evidence: dict[str, Any]) -> Source:
    """Source text: PR title and body when the scan carried them, else the commit's."""
    subject = str(evidence.get("subject") or "")
    pr_title = str(evidence.get("pr_title") or "")
    body = str(evidence.get("pr_body") or "") or str(evidence.get("body") or "")
    title = clean_title(pr_title or subject)
    links = []
    if evidence.get("sha"):
        links.append(f"Commit: {evidence['sha']}")
    if evidence.get("pr_url"):
        links.append(f"Pull request: {evidence['pr_url']}")
    elif evidence.get("pr_number") is not None:
        links.append(f"Pull request: #{evidence['pr_number']}")
    return Source(
        title, title, body.strip() or subject, str(evidence.get("date") or "")[:10], links
    )


def _highest_number(*folders: AdrDir) -> int:
    numbers = [f.number for folder in folders for f in folder.files]
    return max(numbers) if numbers else 0


def _section(heading: str, source: Source, status: str) -> str:
    key = heading.strip().lower()
    if key == "status":
        return status
    if key == "date":
        return source.date or NOT_RECORDED
    if key in CONTEXT_HEADINGS:
        return source.context
    if key in DECISION_HEADINGS:
        return source.decision
    if key in REFERENCE_HEADINGS:
        return "\n".join(f"- {link}" for link in source.links) or NOT_RECORDED
    return NOT_RECORDED


def _frontmatter(style: FolderStyle, adr_id: str, status: str, date: str) -> list[str]:
    if not style.frontmatter_keys:
        return []
    fixed = {
        "id": adr_id,
        "status": status.lower(),
        "date": date or "null",
        "decision-makers": "[]",
        "supersedes": "[]",
        "superseded-by": "null",
        "implemented": "false",
    }
    return ["---", *(f"{k}: {fixed.get(k, 'null')}" for k in style.frontmatter_keys), "---", ""]


def render(style: FolderStyle, number: int, source: Source, status: str) -> str:
    padded = f"{number:0{style.width}d}"
    adr_id = f"{style.prefix}{padded}"
    if style.h1_form == "number-dot":
        heading = f"# {number}. {source.title}"
    else:
        heading = f"# ADR-{padded}: {source.title}"
    lines = _frontmatter(style, adr_id, status, source.date) + [heading, ""]
    for name in style.headings:
        lines += [f"## {name}", "", _section(name, source, status), ""]
    has_references = any(h.strip().lower() in REFERENCE_HEADINGS for h in style.headings)
    if source.links and not has_references:
        lines += ["## Source", "", *(f"- {link}" for link in source.links), ""]
    return "\n".join(lines)


def resolve_target_dir(repo: Path, out_arg: str) -> tuple[Path, list[AdrDir]]:
    """Validate --out. Inside the repository it must equal a folder `locate` reports."""
    repo = repo.resolve()
    named = Path(out_arg).expanduser().absolute()
    out = named.resolve()
    dirs, _ = find_adr_dirs(repo)
    if within(named, repo) and not within(out, repo):
        raise DraftError(2, f"--out {out_arg} is inside the repository but resolves outside it")
    if within(out, repo) and out not in {d.path.resolve() for d in dirs}:
        raise DraftError(2, f"--out {out_arg} is inside the repository but is not an ADR folder")
    if out.exists() and not out.is_dir():
        raise DraftError(2, f"--out {out_arg} is not a directory")
    return out, dirs


def write_draft(scan_file: str, finding_id: str, out_arg: str, status: str) -> dict[str, Any]:
    """Write one draft. Raises DraftError(1) when the target exists, (2) on bad input."""
    scan, finding = load_finding(scan_file, finding_id)
    repo = Path(scan["repo"])
    if not repo.is_dir():
        raise DraftError(2, f"repository in the scan file is not a directory: {repo}")
    out, repo_dirs = resolve_target_dir(repo, out_arg)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DraftError(2, f"cannot create {out_arg}: {exc}") from exc
    target_dir = load_dir(out, "")
    number = max(_highest_number(target_dir, *repo_dirs), 0) + 1
    style = folder_style(target_dir, repo_dirs)
    source = source_from(finding.get("evidence") or {})
    name = f"{style.prefix}{number:0{style.width}d}-{slugify(source.title)}.md"
    target = out / name
    text = render(style, number, source, status)
    try:
        with open(target, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise DraftError(1, f"{target} already exists; not replaced") from exc
    except OSError as exc:
        raise DraftError(2, f"cannot write {target}: {exc}") from exc
    return {"written": str(target), "number": number, "id": finding_id, "status": status}
