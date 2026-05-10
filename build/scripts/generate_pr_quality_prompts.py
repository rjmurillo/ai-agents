#!/usr/bin/env python3
"""Generate .github/prompts/pr-quality-gate-{role}.md from .claude/review-axes/.

Canonical source of PR-quality review prompts is `.claude/review-axes/{role}.md`
(REQ-008-01). This script transforms each canonical file into the CI-side
prompt at `.github/prompts/pr-quality-gate-{role}.md` so CI evaluates the
same criteria as `/review`.

The transform is intentionally narrow and fully declarative (REQ-008-02):

- strip YAML frontmatter keys `name`, `role`, `version`, `description`
- prepend a static 3-line HTML-comment CI header (no timestamps, no SHAs)
- emit canonical body unchanged
- write atomically: temp file in same dir, fsync, os.replace

Idempotency: running the script twice in succession produces zero diff
on `.github/prompts/`. Any time-varying token in the output (timestamp,
git SHA, env-dependent string) breaks idempotency and is forbidden.

Drift detection: `--dry-run` exits 1 with a unified diff if any expected
output differs from the file currently committed at the destination.
This is the contract `.githooks/pre-push` and the CI `drift-check` job
rely on.

EXIT CODES (per ADR-035):
  0 - success (sync clean OR dry-run with no drift)
  1 - logic/drift error (dry-run found differences, source/dest IO error)
  2 - configuration error (canonical dir missing, filename invalid)

Refs #1934 (REQ-008-02, REQ-008-03).
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_DIR = REPO_ROOT / ".claude" / "review-axes"
GENERATED_DIR = REPO_ROOT / ".github" / "prompts"

# Filename regex per REQ-008-02 AC: lowercase + dash, .md extension.
_FILENAME_RE = re.compile(r"^[a-z][a-z0-9_-]*\.md$")

# Static 3-line CI header. No timestamps, no SHAs, no env-dependent tokens.
# {role} is substituted with the axis role name. The static template ensures
# byte-identical output across runs and machines for the same input.
_CI_HEADER_TEMPLATE = (
    "<!-- GENERATED -- DO NOT EDIT -->\n"
    "<!-- Source: .claude/review-axes/{role}.md -->\n"
    "<!-- Run: python3 build/scripts/generate_pr_quality_prompts.py -->\n"
    "\n"
)

# Frontmatter keys stripped from canonical before emitting CI prompt.
_STRIP_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {"name", "role", "version", "description"}
)


class GeneratePromptsError(Exception):
    """Domain error for canonical-to-CI transform."""


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown file into (frontmatter, body).

    Returns ("", text) when no frontmatter is present.
    """
    if not text.startswith("---\n"):
        return "", text
    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        return "", text
    return text[4:end_idx], text[end_idx + 5 :]


def _strip_keys_from_frontmatter(frontmatter: str, keys: frozenset[str]) -> str:
    """Return frontmatter text with the given top-level keys removed.

    Uses a line-oriented scan so it does not require yaml. Top-level keys are
    lines that start at column 0 with `<key>:`. Continuation lines (indented)
    are preserved when their parent key is preserved.
    """
    out_lines: list[str] = []
    skipping_parent = False
    for line in frontmatter.splitlines():
        if not line:
            if not skipping_parent:
                out_lines.append(line)
            continue
        first_char = line[0]
        is_top_level_key = (
            first_char != " " and first_char != "\t" and ":" in line
        )
        if is_top_level_key:
            key = line.split(":", 1)[0].strip()
            if key in keys:
                skipping_parent = True
                continue
            skipping_parent = False
            out_lines.append(line)
        elif not skipping_parent:
            out_lines.append(line)
    return "\n".join(out_lines)


def _validate_filename(name: str) -> None:
    """Reject filenames not matching the canonical regex."""
    if not _FILENAME_RE.match(name):
        raise GeneratePromptsError(
            f"canonical filename does not match {_FILENAME_RE.pattern!r}: {name}"
        )


def _validate_required_frontmatter(frontmatter: str, role: str) -> None:
    """Reject canonical files missing required frontmatter keys.

    PR #1965 cluster T: stripping required keys without first verifying their
    presence let malformed axis files generate CI prompts with no provenance
    metadata. The schema contract in REQ-008-01 requires `name`, `role`,
    `version`, `description`; if any is missing, the file is malformed and
    must not generate.
    """
    required = {"name", "role", "version", "description"}
    keys: set[str] = set()
    for line in frontmatter.splitlines():
        if not line or line[0] in (" ", "\t", "#", "-"):
            continue
        if ":" in line:
            keys.add(line.split(":", 1)[0].strip())
    missing = required - keys
    if missing:
        raise GeneratePromptsError(
            f"canonical {role}.md missing required frontmatter keys: "
            f"{sorted(missing)}"
        )


def transform(canonical_text: str, role: str) -> str:
    """Apply the canonical-to-CI transform.

    Parameters
    ----------
    canonical_text:
        Raw bytes (decoded as UTF-8) of `.claude/review-axes/{role}.md`.
    role:
        Axis role name (filename stem). Substituted into the CI header.

    Returns
    -------
    str
        Transformed CI prompt text. Idempotent: same input always yields
        same output, regardless of time, environment, or git state.

    Raises
    ------
    GeneratePromptsError
        When canonical file is missing required frontmatter keys
        (`name`, `role`, `version`, `description`). PR #1965 cluster T.
    """
    frontmatter, body = _split_frontmatter(canonical_text)
    if frontmatter:
        _validate_required_frontmatter(frontmatter, role)
    if frontmatter:
        stripped = _strip_keys_from_frontmatter(frontmatter, _STRIP_FRONTMATTER_KEYS)
        stripped = stripped.strip()
        if stripped:
            # Preserve any non-stripped frontmatter keys.
            frontmatter_block = f"---\n{stripped}\n---\n\n"
        else:
            frontmatter_block = ""
    else:
        frontmatter_block = ""

    header = _CI_HEADER_TEMPLATE.format(role=role)
    return header + frontmatter_block + body.lstrip("\n")


def _atomic_write(path: Path, content: str) -> None:
    """Write file atomically: temp file in same dir, fsync, os.replace.

    Preserves prior file on crash mid-write.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _list_canonical_files(canonical_dir: Path) -> list[Path]:
    if not canonical_dir.is_dir():
        raise GeneratePromptsError(f"canonical dir missing: {canonical_dir}")
    files: list[Path] = []
    for child in sorted(canonical_dir.iterdir()):
        if child.is_symlink():
            # Reject symlinks: a malicious symlink named `evil.md` could redirect
            # the generator to read content outside the canonical dir, including
            # outside the repo. Canonical files must be plain regular files.
            # CWE-22 path traversal hardening (issue #1934 /test gate finding F6).
            raise GeneratePromptsError(
                f"canonical file must not be a symlink: {child.name}"
            )
        if not child.is_file() or child.suffix != ".md":
            continue
        _validate_filename(child.name)
        files.append(child)
    return files


def _expected_dest_name(canonical_name: str) -> str:
    """`.claude/review-axes/{role}.md` -> `.github/prompts/pr-quality-gate-{role}.md`."""
    return f"pr-quality-gate-{canonical_name}"


def _read_committed_dest(dest: Path) -> str | None:
    """Read dest file from HEAD (committed state), not the working tree.

    Returns the committed content as text, or None if dest is not tracked
    or git is unavailable. The drift check compares against committed
    content per REQ-008-03 AC: "diffs against the HEAD-committed content of
    `.github/prompts/` (not working tree content)". A developer who
    regenerates but forgets to stage/commit would otherwise have a clean
    working tree (drift hook passes) while pushing stale committed prompts.
    PR #1965 copilot review (cluster C).
    """
    try:
        rel = dest.relative_to(REPO_ROOT)
    except ValueError:
        return None
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel.as_posix()}"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def regenerate(
    canonical_dir: Path,
    generated_dir: Path,
    *,
    dry_run: bool,
) -> tuple[int, list[str]]:
    """Regenerate CI prompts from canonical sources.

    Returns
    -------
    tuple[int, list[str]]
        (exit_code, log_lines). exit_code is 0 on success or clean dry-run,
        1 on drift detected during dry-run, 2 on config error.
    """
    log: list[str] = []
    try:
        canonical_files = _list_canonical_files(canonical_dir)
    except GeneratePromptsError as exc:
        return 2, [f"role=ALL status=config_error error={exc}"]

    if not canonical_files:
        return 2, ["role=ALL status=config_error error=no_canonical_files"]

    generated_dir.mkdir(parents=True, exist_ok=True)

    drift_count = 0
    for src in canonical_files:
        role = src.stem
        dest_name = _expected_dest_name(src.name)
        dest = generated_dir / dest_name

        canonical_text = src.read_text(encoding="utf-8")
        expected = transform(canonical_text, role)

        if dry_run:
            # Compare against HEAD-committed content (REQ-008-03 AC). If git
            # is unavailable or dest is untracked, fall back to working-tree
            # so dry-run still functions outside a git repo (e.g. pytest
            # tmp_path fixtures).
            committed = _read_committed_dest(dest)
            current = (
                committed
                if committed is not None
                else (dest.read_text(encoding="utf-8") if dest.exists() else "")
            )
            if current != expected:
                drift_count += 1
                # Use repo-relative paths when possible; fall back to absolute
                # when dest is outside the repo (e.g. pytest tmp_path).
                try:
                    dest_label = str(dest.relative_to(REPO_ROOT))
                except ValueError:
                    dest_label = str(dest)
                try:
                    src_label = str(src.relative_to(REPO_ROOT))
                except ValueError:
                    src_label = str(src)
                diff = "\n".join(
                    difflib.unified_diff(
                        current.splitlines(),
                        expected.splitlines(),
                        fromfile=dest_label,
                        tofile=f"expected from {src_label}",
                        lineterm="",
                    )
                )
                log.append(f"role={role} status=drift")
                # Drift diff goes to stderr in main(); store for return.
                log.append(diff)
            else:
                log.append(f"role={role} status=ok")
        else:
            _atomic_write(dest, expected)
            log.append(f"role={role} status=written")

    if dry_run and drift_count > 0:
        log.append(f"role=ALL status=drift count={drift_count}")
        return 1, log

    log.append(f"role=ALL status=ok count={len(canonical_files)}")
    return 0, log


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate .github/prompts/pr-quality-gate-*.md from "
            ".claude/review-axes/*.md. Idempotent. ADR-035 exit codes."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Compare expected output against committed files; exit 1 with "
            "unified diff on stderr if drift detected. Used by pre-push hook "
            "and CI drift-check job."
        ),
    )
    args = parser.parse_args(argv)

    code, log = regenerate(CANONICAL_DIR, GENERATED_DIR, dry_run=args.dry_run)
    # Status lines (`role=...`, `status=...`) -> stdout for grep-friendly
    # consumers. Anything else (unified diff blocks for drift cases) ->
    # stderr per the --dry-run help text contract. PR #1965 cluster L:
    # the prior `line.startswith("---")` check matched the diff `--- file`
    # header and routed the diff to stdout, contradicting the help text
    # and the comment in regenerate().
    for line in log:
        if line.startswith("role=") or "status=" in line:
            print(line)
        else:
            print(line, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
