#!/usr/bin/env python3
"""Export and validate a reusable audit manifest for one skill-doctor run.

The manifest records what a run declared and what it found, so a reviewer can
inspect the scope and the skill catalog without the private conversations:

  - declared inputs, evidence caps, window, and branch policy
  - a source revision (sha256 over the skill-doctor scripts)
  - upstream identity evidence for each included root, read from Git metadata
    files only (never by running Git, never from a directory name)
  - the scope resolution (included and rejected roots)
  - the catalog: one definition per distinct content, identical copies as aliases
  - an attribution summary that stays unresolved wherever the transcript is silent

Uncertainty (unresolved attribution, rejected roots) is recorded, not failed.
Validation rejects only contradictions: an included root nobody authorized, two
roots of one Git common directory reporting different origins, or a claimed
shared upstream that the identity evidence contradicts. A current content hash
identifies today's file. It never verifies what a historical session executed.

Usage: audit_manifest.py MANIFEST.json   (exit 0 valid, 1 invalid, 2 bad input)

Python 3.10+, stdlib only. Nothing is uploaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from repository_scope import common_dir_of, git_dir_of

MANIFEST_VERSION = 1
MANIFEST_FILENAME = "audit_manifest.json"
HISTORICAL_NOTE = (
    "A current content hash identifies today's file only. It never verifies the "
    "definition a historical session executed."
)
_TIMESTAMP_KEYS = frozenset({"generated_at"})
_REQUIRED_KEYS = (
    "manifest_version",
    "fingerprint",
    "declared_inputs",
    "window_days",
    "evidence_caps",
    "branch_policy",
    "source_revision",
    "upstream_identity",
    "upstream_claims",
    "scope_resolution",
    "catalog",
    "attribution",
)
_CAP_KEYS = ("max_sessions", "per_skill", "no_skill", "min_idle_minutes", "include_subagents")
_REMOTE_HEADER = re.compile(r'^\s*\[\s*remote\s+"([^"]*)"\s*\]')
_ANY_HEADER = re.compile(r"^\s*\[")
_URL_LINE = re.compile(r"^\s*url\s*=\s*(.*?)\s*$", re.IGNORECASE)


def inputs_from_args(args: Any) -> dict[str, Any]:
    """Collect the run inputs a manifest declares from parsed collector arguments."""
    return {
        "harness": args.harness,
        "include_global_skills": bool(args.include_global_skills),
        "no_worktrees": bool(args.no_worktrees),
        "explicit_repos": list(args.repo or []),
        "max_sessions": args.max_sessions,
        "per_skill": args.per_skill,
        "no_skill": args.no_skill,
        "min_idle_minutes": args.min_idle_minutes,
        "include_subagents": bool(args.include_subagents),
    }


def source_revision(scripts_dir: Path | None = None) -> dict[str, Any]:
    """Hash the script files in sorted name order. No Git needed."""
    directory = scripts_dir or Path(__file__).resolve().parent
    digest = hashlib.sha256()
    count = 0
    for path in sorted(item for item in directory.iterdir() if item.is_file()):
        digest.update(path.name.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\0")
        count += 1
    return {"algorithm": "sha256-over-sorted-files", "sha256": digest.hexdigest(), "files": count}


def _redact_url(url: str) -> str:
    """Drop credentials from a URL so the manifest never carries them."""
    parts = urlsplit(url)
    if parts.scheme and parts.netloc and "@" in parts.netloc:
        return urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[1]))
    return url


def normalize_upstream(url: str | None) -> str | None:
    """Compare-friendly form: no credentials, no trailing slash or .git, lower-case host."""
    if not url:
        return None
    text = _redact_url(url.strip())
    parts = urlsplit(text)
    if parts.scheme and parts.netloc:
        path = parts.path.rstrip("/").removesuffix(".git")
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))
    return text.rstrip("/").removesuffix(".git")


def read_origin_url(common: Path) -> str | None:
    """Read ``[remote "origin"] url`` from ``<common>/config`` without running Git."""
    try:
        lines = (common / "config").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    in_origin = False
    for line in lines:
        header = _REMOTE_HEADER.match(line)
        if header:
            in_origin = header.group(1) == "origin"
        elif _ANY_HEADER.match(line):
            in_origin = False
        elif in_origin:
            match = _URL_LINE.match(line)
            if match and match.group(1):
                return _redact_url(match.group(1).strip('"'))
    return None


def _identity_for(root: Path) -> dict[str, Any]:
    git_dir = git_dir_of(root)
    if git_dir is None:
        return {
            "path": str(root),
            "common_dir": None,
            "origin_url": None,
            "evidence": "no-git-metadata",
        }
    common = common_dir_of(git_dir)
    url = read_origin_url(common)
    return {
        "path": str(root),
        "common_dir": str(common),
        "origin_url": url,
        "evidence": "git-config" if url else "no-origin-remote",
    }


def _scope_of(path: str, roots: list[Path]) -> str:
    target = Path(path)
    for root in roots:
        if target == root or root in target.parents:
            return "repository"
    return "global-or-extra"


def _catalog(skills: Any, roots: list[Path]) -> list[dict[str, Any]]:
    entries = []
    for skill in skills:
        for definition in skill.get("definitions", []):
            paths = sorted(definition["paths"])
            entries.append(
                {
                    "name": skill["name"],
                    "sha256": definition["sha256"],
                    "path": paths[0],
                    "scope": _scope_of(paths[0], roots),
                    "aliases": paths[1:],
                    "current_edit_target": definition["sha256"] == skill.get("sha256"),
                }
            )
    return sorted(entries, key=lambda entry: (entry["name"], entry["sha256"]))


def _attribution(sessions: Any) -> dict[str, Any]:
    kinds: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    unresolved = flagged_sessions = 0
    for session in sessions:
        notes = session.get("skill_attribution") or {}
        flagged_sessions += 1 if notes else 0
        for note in notes.values():
            kinds[note.get("evidence", "unknown")] += 1
            unresolved += 1 if note.get("unresolved_because") else 0
            reasons.update(note.get("unresolved_because") or [])
    return {
        "evidence_kinds": dict(sorted(kinds.items())),
        "unresolved_count": unresolved,
        "unresolved_reasons": dict(sorted(reasons.items())),
        "sessions_with_unresolved": flagged_sessions,
        "verified_count": 0,
        "historical_verification": "none",
        "note": HISTORICAL_NOTE,
    }


def _scope_report(inventory: dict[str, Any]) -> dict[str, Any]:
    scope = inventory["scope_resolution"]
    return {
        "clone_discovery": scope["clone_discovery"],
        "included": [dict(root) for root in scope["included"]],
        "rejected": [dict(root) for root in scope["rejected"]],
    }


def _fingerprint(manifest: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in manifest.items()
        if key not in _TIMESTAMP_KEYS and key != "fingerprint"
    }
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_manifest(
    inventory: dict[str, Any],
    run_inputs: dict[str, Any],
    *,
    scripts_dir: Path | None = None,
    upstream_claims: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the manifest from an inventory dict and the run's declared inputs."""
    included = [Path(root["path"]) for root in inventory["scope_resolution"]["included"]]
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "declared_inputs": {
            "conversation_scope": inventory["conversation_scope"],
            "repos": list(inventory["repos"]),
            "explicit_repos": sorted(run_inputs.get("explicit_repos", [])),
            "harness": run_inputs.get("harness", inventory.get("harness")),
            "include_global_skills": bool(run_inputs.get("include_global_skills")),
            "no_worktrees": bool(run_inputs.get("no_worktrees")),
        },
        "window_days": inventory["window_days"],
        "evidence_caps": {key: run_inputs.get(key) for key in _CAP_KEYS},
        "branch_policy": {"branch_filter": inventory["scope_resolution"]["branch_filter"]},
        "source_revision": source_revision(scripts_dir),
        "upstream_identity": [_identity_for(root) for root in included],
        "upstream_claims": [dict(claim) for claim in upstream_claims or []],
        "scope_resolution": _scope_report(inventory),
        "catalog": _catalog(inventory.get("skills", []), included),
        "attribution": _attribution(inventory.get("sessions", [])),
    }
    manifest["fingerprint"] = _fingerprint(manifest)
    return manifest


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write atomically: a temp file in the target directory, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def export_manifest(inventory: dict[str, Any], args: Any, out: Path) -> None:
    """Write a validated manifest next to inventory.json; exit 1 when evidence contradicts scope."""
    manifest = build_manifest(inventory, inputs_from_args(args))
    errors = validate_manifest(manifest)
    if errors:
        for error in errors:
            print(f"error: audit manifest rejected: {error}", file=sys.stderr)
        sys.exit(1)
    write_manifest(out / MANIFEST_FILENAME, manifest)
    print(f"audit manifest:    {out / MANIFEST_FILENAME}")


def _check_shape(manifest: Any) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors = [f"missing field: {key}" for key in _REQUIRED_KEYS if key not in manifest]
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        errors.append(
            f"unsupported manifest_version: {manifest.get('manifest_version')!r} "
            f"(expected {MANIFEST_VERSION})"
        )
    return errors


def _check_fingerprint(manifest: dict[str, Any]) -> list[str]:
    if manifest["fingerprint"] != _fingerprint(manifest):
        return ["fingerprint does not match the manifest content"]
    return []


def _check_attribution(manifest: dict[str, Any]) -> list[str]:
    attribution = manifest["attribution"]
    errors = []
    if attribution.get("historical_verification") != "none":
        errors.append("attribution claims historical verification from a current hash")
    if attribution.get("verified_count", 0) != 0:
        errors.append("attribution reports hash-only verified executions")
    for entry in manifest["catalog"]:
        if any("verified" in key or "executed" in key for key in entry):
            errors.append(f"catalog entry {entry.get('name')!r} claims execution verification")
    return errors


def _group_by_common_dir(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in manifest["upstream_identity"]:
        groups.setdefault(item.get("common_dir") or f"none:{item['path']}", []).append(item)
    return groups


def _check_authorization(manifest: dict[str, Any]) -> list[str]:
    declared = set(manifest["declared_inputs"]["repos"])
    selected = {
        root["path"]
        for root in manifest["scope_resolution"]["included"]
        if root.get("kind") == "selected" and root["path"] in declared
    }
    groups = _group_by_common_dir(manifest)
    errors = [
        f"unauthorized root: {item['path']} (no explicitly selected checkout shares its repository)"
        for items in groups.values()
        if not any(item["path"] in selected for item in items)
        for item in items
    ]
    if len(groups) > 1 and not manifest["declared_inputs"]["explicit_repos"]:
        errors.append("multiple repositories require each clone to be passed as --repo")
    unexplained = {item["path"] for items in groups.values() for item in items}
    included = {root["path"] for root in manifest["scope_resolution"]["included"]}
    errors.extend(
        f"identity evidence missing for root: {p}" for p in sorted(included - unexplained)
    )
    return errors


def _check_shared_dir_identity(manifest: dict[str, Any]) -> list[str]:
    errors = []
    for common, items in _group_by_common_dir(manifest).items():
        urls = {normalize_upstream(item.get("origin_url")) for item in items}
        if len(items) > 1 and len(urls) > 1:
            errors.append(f"conflicting origin URLs for roots sharing Git common dir {common}")
    return errors


def _check_claims(manifest: dict[str, Any]) -> list[str]:
    identity = {
        item["path"]: normalize_upstream(item.get("origin_url"))
        for item in manifest["upstream_identity"]
    }
    errors = []
    for claim in manifest["upstream_claims"]:
        claimed = normalize_upstream(claim.get("upstream"))
        for root in claim.get("roots", []):
            if root not in identity:
                errors.append(f"shared-upstream claim names a root that is not included: {root}")
            elif claimed is None or identity[root] != claimed:
                errors.append(
                    f"conflicting shared-upstream claim for {root}: evidence is "
                    f"{identity[root]!r}, claim is {claimed!r}"
                )
    return errors


def _check_catalog(manifest: dict[str, Any]) -> list[str]:
    errors = []
    seen = set()
    for entry in manifest["catalog"]:
        key = (entry.get("name"), entry.get("sha256"))
        if key in seen:
            errors.append(f"duplicate catalog definition: {key[0]!r} {key[1]!r}")
        seen.add(key)
        if entry.get("path") in entry.get("aliases", []):
            errors.append(f"alias repeats the definition path for {entry.get('name')!r}")
    return errors


def validate_manifest(manifest: Any) -> list[str]:
    """Return every contract violation; an empty list means the manifest is valid."""
    errors = _check_shape(manifest)
    if errors:
        return errors
    checks = (
        _check_fingerprint,
        _check_attribution,
        _check_authorization,
        _check_shared_dir_identity,
        _check_claims,
        _check_catalog,
    )
    try:
        return [error for check in checks for error in check(manifest)]
    except (KeyError, TypeError, AttributeError) as exc:
        return [f"malformed manifest structure: {type(exc).__name__}: {exc}"]


def _parse(argv: list[str]) -> argparse.Namespace | int:
    parser = argparse.ArgumentParser(description="Validate a skill-doctor audit manifest.")
    parser.add_argument("manifest", help="path to audit_manifest.json")
    try:
        return parser.parse_args(argv)
    except SystemExit as exit_request:
        return exit_request.code if isinstance(exit_request.code, int) else 2


def main(argv: list[str] | None = None) -> int:
    """Validate a manifest file. Exit 0 valid, 1 invalid, 2 bad arguments or unreadable."""
    parsed = _parse(sys.argv[1:] if argv is None else argv)
    if isinstance(parsed, int):
        return parsed
    try:
        text = Path(parsed.manifest).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {parsed.manifest}: {exc}", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(text)
    except ValueError as exc:
        print(f"invalid: not valid JSON: {exc}", file=sys.stderr)
        return 1
    errors = validate_manifest(manifest)
    for error in errors:
        print(f"invalid: {error}", file=sys.stderr)
    if errors:
        return 1
    print(
        f"valid: manifest_version {manifest['manifest_version']}, fingerprint {manifest['fingerprint']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
