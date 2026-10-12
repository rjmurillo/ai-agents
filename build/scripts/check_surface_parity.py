#!/usr/bin/env python3
"""Surface parity gate: one manifest says who is authoritative for each shipped copy.

Issue #5637. The repository ships the same content through many trees:
generator outputs, binplaced install copies, translated projections, and
hand-maintained siblings. ``build_all.py --check`` proves the generator-owned
ones are fresh, but nothing said which trees exist, which source each one
answers to, or which hand-maintained copies no generator can see. This module
reads ``templates/platforms/surface-parity.yaml`` and answers those questions.

Relations (``relation:`` in the manifest)
-----------------------------------------

``generated``
    A generator renders the surface from ``authority``. Freshness belongs to
    ``build_all.py --check``; this module checks the declaration (generator
    and authority exist) and labels any stale path the generator run leaves.
``binplaced``
    A byte copy made by ``binplace_manifest.py`` from a plugin tree. Each
    ``binplace.yaml`` row must have a matching surface.
``mirrored``
    A byte-identical copy of ``authority``. With a ``generator`` the
    generator owns freshness. Without one it is hand-maintained, and this
    module compares the bytes itself.
``translated``
    A copy that differs on purpose (frontmatter remap, import rewrite, path
    rename). With a ``generator`` the generator owns the translation. Without
    one, ``divergent`` lists the only files allowed to differ; every other
    shared file must be byte-identical.
``independent``
    Authored in place. Never compared, and a generator that rewrites it is a
    violation.

Findings
--------

``UNMANIFESTED``  generator metadata names a path no surface covers.
``UNCLASSIFIED``  a file under a manifest root belongs to no surface.
``AMBIGUOUS``     two surfaces claim a file with equal specificity.
``MISSING-GENERATOR`` / ``MISSING-AUTHORITY``  a declared path does not exist.
``MISSING``       an authority file has no copy in a hand-maintained surface.
``STALE``         a hand-maintained copy differs from its authority.
``EXTRA``         a copy has no authority file and the surface forbids extras.
``EXCLUSION-VIOLATED``  an ``authority_exclude`` name exists in the copy.
``DIVERGENT-INVALID``   a ``divergent`` entry is identical or has no authority.
``STALE-<relation>``    ``build_all.py --check`` left this path changed.
``WROTE-INDEPENDENT``   a generator changed an independent surface.

Discovery
---------

The inventory is not hard-coded here. ``binplace.yaml`` rows, the
``artifacts`` output paths in every platform YAML, and ``OWNED_PREFIXES`` in
``build_all.py`` are read at run time; any path they name that no surface
covers is ``UNMANIFESTED``. Deleting a manifest row therefore fails the gate
instead of silencing it.

CLI::

    uv run python build/scripts/check_surface_parity.py
    uv run python build/scripts/check_surface_parity.py --format json

The standalone CLI checks declarations, inventory, classification, and
hand-maintained bytes only. It never runs a generator, so generated-output
drift is caught by ``build_all.py --check`` and
``agent-drift-detection.yml``, not here.

``build_all.py --check`` runs the same checks and also labels its stale-path
list with :func:`classify_changes`, so CI and local runs share one result.

EXIT CODES (ADR-035)
--------------------
0 - every surface holds
1 - one or more findings
2 - the manifest or a generator metadata file is missing or malformed
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path, PurePosixPath

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import binplace_manifest  # noqa: E402
from surface_manifest import (  # noqa: E402
    MANIFEST_REL,
    Finding,
    Manifest,
    Surface,
    SurfaceManifestError,
    join,
    list_files,
    load_manifest,
    matches,
    owner_of,
    rel_to,
)
from yaml_loader import ConfigError, load_platform_config  # noqa: E402

PLATFORMS_REL = "templates/platforms"
_OUTPUT_KEYS = ("outputDir", "outputDirs", "outputConfig", "outputScripts")
_REPORT_LIMIT = 60

# --- Checks ----------------------------------------------------------------


def check_declarations(repo_root: Path, manifest: Manifest) -> list[Finding]:
    """Generators and authorities must exist; excluded names must stay out."""
    findings: list[Finding] = []
    for s in manifest.surfaces:
        if s.generator and not (repo_root / s.generator).is_file():
            findings.append(Finding("MISSING-GENERATOR", s.id, s.generator, "no such file"))
        if s.authority and not (repo_root / s.authority).exists():
            findings.append(Finding("MISSING-AUTHORITY", s.id, s.authority, "no such path"))
        findings.extend(_exclusion_findings(repo_root, s))
    return findings


def _exclusion_findings(repo_root: Path, s: Surface) -> list[Finding]:
    findings: list[Finding] = []
    for name in s.authority_exclude:
        if s.authority and not (repo_root / s.authority / name).exists():
            findings.append(
                Finding("EXCLUSION-UNKNOWN", s.id, f"{s.authority}/{name}", "excluded name absent")
            )
        copy = repo_root / s.path / name
        if copy.exists():
            findings.append(
                Finding("EXCLUSION-VIOLATED", s.id, f"{s.path}/{name}", "must not ship here")
            )
    return findings


def _covered(manifest: Manifest, path: str) -> bool:
    """A surface sits at or under ``path``, or an unrestricted ancestor owns it.

    An ancestor row with ``include`` owns only the globbed names, so it cannot
    vouch for a new output beneath it.
    """
    return any(
        rel_to(s.path, path) is not None or (rel_to(path, s.path) is not None and not s.include)
        for s in manifest.surfaces
    )


def _prefix_covered(manifest: Manifest, prefix: str) -> bool:
    """A surface sits at or under the owned prefix."""
    clean = prefix.rstrip("/")
    return any(rel_to(s.path, clean) is not None for s in manifest.surfaces)


def _surfaces_at(manifest: Manifest, path: str) -> list[Surface]:
    return [s for s in manifest.surfaces if s.path == path]


def _relative_or_none(repo_root: Path, path: Path | None) -> str | None:
    return None if path is None else path.relative_to(repo_root).as_posix()


def _install_hit(surface: Surface, plugin: str | None) -> bool:
    if plugin is None:
        return bool(surface.relation != "independent")
    return bool(surface.relation == "binplaced" and surface.authority == plugin)


def _binplace_findings(repo_root: Path, manifest: Manifest) -> list[Finding]:
    findings: list[Finding] = []
    for row in binplace_manifest.load(repo_root):
        install = _relative_or_none(repo_root, row.install_tree)
        plugin = _relative_or_none(repo_root, row.plugin_tree)
        source = f"binplace row {row.class_name}"
        if install is not None and not any(
            _install_hit(s, plugin) for s in _surfaces_at(manifest, install)
        ):
            findings.append(_unmanifested(source, install))
        if plugin is not None and not any(
            s.relation in {"generated", "mirrored", "translated"}
            for s in _surfaces_at(manifest, plugin)
        ):
            findings.append(_unmanifested(source, plugin))
    return findings


def _unmanifested(source: str, path: str) -> Finding:
    return Finding("UNMANIFESTED", "", path, f"named by {source}; add a surface")


def _is_platform_config(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return any(line.startswith(("provider:", "platform:")) for line in text.splitlines())


def _stanza_outputs(stanza: object) -> list[str]:
    if not isinstance(stanza, dict):
        return []
    outputs: list[str] = []
    for key in _OUTPUT_KEYS:
        value = stanza.get(key)
        if isinstance(value, str):
            outputs.append(value.rstrip("/"))
        elif isinstance(value, list):
            outputs.extend(v.rstrip("/") for v in value if isinstance(v, str))
    return outputs


def _platform_findings(repo_root: Path, manifest: Manifest) -> list[Finding]:
    findings: list[Finding] = []
    platforms_dir = repo_root / PLATFORMS_REL
    for cfg in sorted(platforms_dir.glob("*.yaml")):
        if not _is_platform_config(cfg):
            continue
        doc = load_platform_config(cfg)
        for section in ("artifacts", "legacy"):
            findings.extend(_section_findings(manifest, cfg.name, section, doc.get(section)))
    return findings


def _section_findings(
    manifest: Manifest, cfg_name: str, section: str, body: object
) -> list[Finding]:
    """Uncovered output paths in one platform section.

    ``artifacts`` holds a stanza per kind. ``legacy`` is one stanza and still
    names the agent output directories (``.github/agents``, ``src/vs-code-agents``).
    """
    if not isinstance(body, dict):
        return []
    stanzas = body.items() if section == "artifacts" else [("", body)]
    return [
        _unmanifested(f"{cfg_name} {section}{'.' + kind if kind else ''}", output)
        for kind, stanza in stanzas
        for output in _stanza_outputs(stanza)
        if not _covered(manifest, output)
    ]


def _prefix_findings(manifest: Manifest, owned_prefixes: Iterable[str]) -> list[Finding]:
    return [
        _unmanifested("build_all.py OWNED_PREFIXES", prefix)
        for prefix in owned_prefixes
        if not _prefix_covered(manifest, prefix)
    ]


def check_inventory(
    repo_root: Path, manifest: Manifest, owned_prefixes: Iterable[str] = ()
) -> list[Finding]:
    """Every path generator metadata names must be covered by a surface."""
    return [
        *_binplace_findings(repo_root, manifest),
        *_platform_findings(repo_root, manifest),
        *_prefix_findings(manifest, owned_prefixes),
    ]


def check_classification(manifest: Manifest, files: Sequence[str]) -> list[Finding]:
    """Every file under a root must belong to exactly one most-specific surface."""
    findings: list[Finding] = []
    for path in files:
        if not any(rel_to(path, root) is not None for root in manifest.roots):
            continue
        owner, ambiguous = owner_of(manifest, path)
        if owner is None:
            findings.append(Finding("UNCLASSIFIED", "", path, "no surface owns this file"))
        elif ambiguous:
            findings.append(Finding("AMBIGUOUS", owner.id, path, "two surfaces tie"))
    return findings


def _authority_rels(surface: Surface, files: Sequence[str]) -> list[str]:
    rels = [r for f in files if (r := rel_to(f, surface.authority or "")) is not None]
    return [r for r in rels if matches(surface, r) and not _is_excluded(surface, r)]


def _is_excluded(surface: Surface, rel: str) -> bool:
    return bool(rel) and PurePosixPath(rel).parts[0] in surface.authority_exclude


def _compare_pair(repo_root: Path, surface: Surface, rel: str, present: set[str]) -> Finding | None:
    source = join(surface.authority or "", rel)
    copy = join(surface.path, rel)
    if copy not in present:
        return Finding("MISSING", surface.id, copy, f"no copy of {source}")
    same = (repo_root / copy).read_bytes() == (repo_root / source).read_bytes()
    allowed = surface.divergent is not None and rel in surface.divergent
    if same or allowed:
        return None
    return Finding("STALE", surface.id, copy, f"differs from {source}")


def _divergence_findings(repo_root: Path, surface: Surface, rels: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for rel in surface.divergent or ():
        if rel not in rels:
            findings.append(
                Finding("DIVERGENT-INVALID", surface.id, rel, "names no authority file")
            )
            continue
        a = repo_root / join(surface.authority or "", rel)
        c = repo_root / join(surface.path, rel)
        if c.is_file() and a.read_bytes() == c.read_bytes():
            findings.append(
                Finding("DIVERGENT-INVALID", surface.id, rel, "identical; drop it from divergent")
            )
    return findings


def _extra_findings(
    manifest: Manifest, surface: Surface, files: Sequence[str], expected: set[str]
) -> list[Finding]:
    if surface.extras == "allow":
        return []
    findings: list[Finding] = []
    for f in files:
        rel = rel_to(f, surface.path)
        if rel is None or rel in expected or not matches(surface, rel):
            continue
        if owner_of(manifest, f)[0] is surface and not _is_excluded(surface, rel):
            findings.append(Finding("EXTRA", surface.id, f, "no authority file"))
    return findings


def check_hand_maintained(
    repo_root: Path, manifest: Manifest, files: Sequence[str]
) -> list[Finding]:
    """Byte-compare every hand-maintained copy against its authority."""
    present = set(files)
    findings: list[Finding] = []
    for surface in manifest.surfaces:
        if not surface.hand_maintained:
            continue
        rels = {
            r
            for r in _authority_rels(surface, files)
            if owner_of(manifest, join(surface.path, r))[0] is surface
        }
        for rel in sorted(rels):
            found = _compare_pair(repo_root, surface, rel, present)
            if found:
                findings.append(found)
        findings.extend(_divergence_findings(repo_root, surface, rels))
        findings.extend(_extra_findings(manifest, surface, files, rels))
    return findings


def run_checks(
    repo_root: Path, manifest: Manifest, *, owned_prefixes: Iterable[str] = ()
) -> list[Finding]:
    """Run every static check and return the combined findings.

    Raises :class:`binplace_manifest.BinplaceConfigError` or
    :class:`yaml_loader.ConfigError` when generator metadata is malformed.
    """
    files = list_files(repo_root)
    return [
        *check_declarations(repo_root, manifest),
        *check_inventory(repo_root, manifest, owned_prefixes),
        *check_classification(manifest, files),
        *check_hand_maintained(repo_root, manifest, files),
    ]


def classify_changes(manifest: Manifest, paths: Iterable[str]) -> list[Finding]:
    """Label paths a generator run left changed with the surface that owns them."""
    findings: list[Finding] = []
    for path in sorted(set(paths)):
        owner, _ = owner_of(manifest, path)
        if owner is None:
            findings.append(Finding("UNCLASSIFIED", "", path, "stale path owned by no surface"))
        elif owner.relation == "independent":
            findings.append(
                Finding("WROTE-INDEPENDENT", owner.id, path, "a generator rewrote authored content")
            )
        else:
            fix = owner.generator or "edit the copy by hand"
            detail = f"authority {owner.authority}; regenerate via {fix}; gate {owner.owner}"
            findings.append(Finding(f"STALE-{owner.relation}", owner.id, path, detail))
    return findings


# --- CLI -------------------------------------------------------------------


def format_report(findings: Sequence[Finding], *, limit: int = _REPORT_LIMIT) -> list[str]:
    """Render findings one per line, capped at ``limit`` with a remainder count."""
    lines = [f.render() for f in findings[:limit]]
    if len(findings) > limit:
        lines.append(f"... and {len(findings) - limit} more")
    return lines


def _find_repo_root(start: Path) -> Path:
    here = start.resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise FileNotFoundError(f"Could not find repo root from {start}")


def _cli_prefixes() -> tuple[str, ...]:
    import build_all  # lazy: build_all imports this module at load time

    return tuple(build_all.OWNED_PREFIXES)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        repo_root = args.repo_root or _find_repo_root(Path.cwd())
        manifest = load_manifest(repo_root)
        if manifest is None:
            print(f"ERROR: {MANIFEST_REL} not found under {repo_root}", file=sys.stderr)
            return 2
        findings = run_checks(repo_root, manifest, owned_prefixes=_cli_prefixes())
    except (
        FileNotFoundError,
        SurfaceManifestError,
        binplace_manifest.BinplaceConfigError,
        ConfigError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps([asdict(f) | {"line": f.render()} for f in findings], indent=2))
    else:
        print("\n".join(format_report(findings)))
        verdict = f"FAIL: {len(findings)} surface parity finding(s)" if findings else "OK"
        print(f"{verdict} across {len(manifest.surfaces)} surfaces")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
