#!/usr/bin/env python3
"""Detect unused, undeclared, and misplaced Python dependencies with deptry.

deptry reads each ``pyproject.toml`` and compares the declared dependencies
with the imports in the code beside it. This wrapper adds what deptry cannot
know about this repository:

* Skill and hook scripts import their sibling modules by bare name, resolved
  through ``sys.path`` at run time (``import github_core``). deptry reports each
  as DEP001 (missing from the dependency definitions). The wrapper hands deptry
  the stem of every tracked ``.py`` file and every tracked directory name as
  ``known_first_party``, so DEP001 stays live for real third-party imports.
  A name that is also a declared dependency's import name is never treated as
  first party, so a local ``yaml.py`` cannot hide the PyYAML dependency.
* Command-line tools and pytest plugins (ruff, mypy, pytest-xdist, ...) are
  never imported, so deptry always reports them as DEP002 (unused). Each
  one is listed in the policy file with a reason and an evidence pattern that
  must still match a tracked file. When the evidence disappears, or the tool
  becomes importable, the exemption itself fails as stale.

The policy lives in ``.github/dependency-hygiene/policy.toml``. Findings of any
other kind (DEP001 to DEP005) fail the run with no exemption mechanism: fix the
manifest or the import.

ADR-006 keeps the logic in a testable Python module; ADR-042 mandates Python.

Exit codes (ADR-035):
    0 - every manifest is clean
    1 - unused, undeclared, misplaced, or stale-exemption findings
    2 - policy or manifest is missing or malformed
    3 - deptry is unavailable or failed to produce a report
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# A direct script run puts only this directory on sys.path, and tests load the
# file by path, so the sibling policy module is made importable explicitly.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dependency_hygiene_policy import (  # noqa: E402
    FixtureModule,
    Manifest,
    PolicyError,
    ToolOnly,
    TransitiveOk,
    load_policy,
    normalize,
)
from dependency_manifest import declared_packages, project_name  # noqa: E402

__all__ = [
    "FixtureModule",
    "Manifest",
    "PolicyError",
    "ToolOnly",
    "TransitiveOk",
    "load_policy",
    "normalize",
]

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

RUN_TIMEOUT_SECONDS = 600

DEFAULT_POLICY = Path(".github") / "dependency-hygiene" / "policy.toml"


@dataclass(frozen=True, slots=True)
class Finding:
    manifest: str
    code: str
    module: str
    where: str
    message: str

    def render(self) -> str:
        return f"{self.manifest}: {self.code} {self.module} ({self.where}): {self.message}"


def tracked_files(root: Path) -> list[str]:
    """List tracked and unignored untracked paths.

    Raises RuntimeError when git is missing or fails: an empty list would
    silently disable evidence tracking and first-party discovery.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            check=False,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git ls-files timed out after {RUN_TIMEOUT_SECONDS}s") from exc
    except OSError as exc:
        raise RuntimeError(f"cannot list tracked files: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()[-300:]
        raise RuntimeError(f"git ls-files failed in {root} (exit {result.returncode}): {detail}")
    return [p for p in result.stdout.decode("utf-8", "replace").split("\0") if p]


def installed_third_party_modules(own_distribution: str | None) -> set[str]:
    """Top-level import names that installed distributions provide.

    Includes undeclared distributions. A name provided only by the manifest's own
    distribution (an editable install of this project) stays out, so the
    project's packages remain first party.
    """
    own = normalize(own_distribution) if own_distribution else None
    modules: set[str] = set()
    for module, distributions in importlib.metadata.packages_distributions().items():
        if any(normalize(dist) != own for dist in distributions):
            modules.add(module)
    return modules


def first_party_names(files: list[str], manifest_dir: str, declared_modules: set[str]) -> list[str]:
    """Module-like names that tracked files make importable by bare name.

    ``declared_modules`` holds import names that belong to third-party
    distributions and so are never first party.
    """
    prefix = "" if manifest_dir in ("", ".") else manifest_dir.rstrip("/") + "/"
    names: set[str] = set()
    for file in files:
        if not file.startswith(prefix):
            continue
        parts = Path(file[len(prefix) :]).parts
        if not parts:
            continue
        if parts[-1].endswith(".py"):
            names.add(Path(parts[-1]).stem)
        names.update(parts[:-1])
    valid = {n for n in names if n.isidentifier()}
    return sorted(valid - declared_modules)


def module_names_for(packages: set[str], module_map: dict[str, tuple[str, ...]]) -> set[str]:
    """Import names a declared package may provide (default mapping plus overrides)."""
    modules: set[str] = set()
    for package in packages:
        modules.add(package.replace("-", "_"))
        modules.update(module_map.get(package, ()))
    return modules


def deptry_args(manifest: Manifest, first_party: list[str]) -> list[str]:
    """CLI flags carrying the settings deptry would read from [tool.deptry].

    ``--config`` cannot be used: deptry resolves the manifest beside the config
    file, so a generated config would hide the real ``pyproject.toml``.
    """
    args: list[str] = []
    for pattern in manifest.extend_exclude:
        args += ["--extend-exclude", f".*{re.escape(pattern)}"]
    for group in manifest.dev_groups:
        args += ["--optional-dependencies-dev-groups", group]
    if manifest.module_map:
        pairs = ",".join(
            f"{package}={'|'.join(modules)}"
            for package, modules in sorted(manifest.module_map.items())
        )
        args += ["--package-module-name-map", pairs]
    for name in first_party:
        args += ["--known-first-party", name]
    return args


def run_deptry(manifest_dir: Path, extra_args: list[str]) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="deptry-") as tmp:
        report = Path(tmp) / "report.json"
        # Keep the tracked module inventory off the OS command line.
        launch = (
            "import json, runpy, sys; "
            "sys.argv.extend(json.load(sys.stdin)); "
            "runpy.run_module('deptry', run_name='__main__', alter_sys=True)"
        )
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    launch,
                    str(manifest_dir),
                    "--no-ansi",
                    "--json-output",
                    str(report),
                ],
                input=json.dumps(extra_args),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                cwd=manifest_dir,
                timeout=RUN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"deptry timed out after {RUN_TIMEOUT_SECONDS}s") from exc
        except OSError as exc:
            raise RuntimeError(f"cannot launch deptry: {exc}") from exc
        if result.returncode not in (0, 1):
            raise RuntimeError(
                f"deptry failed with exit {result.returncode}: {result.stderr[-500:]}"
            )
        if not report.exists():
            raise RuntimeError(
                "deptry produced no report (is it installed? run via "
                "'uv run --frozen --extra dev'): "
                f"exit {result.returncode}: {result.stderr.strip()[-500:]}"
            )
        try:
            report_data = json.loads(report.read_text(encoding="utf-8"))
            if not isinstance(report_data, list) or any(
                not isinstance(item, dict)
                or not isinstance(item.get("error"), dict)
                or not isinstance(item["error"].get("code"), str)
                or not isinstance(item["error"].get("message"), str)
                or not isinstance(item.get("module"), str)
                or not isinstance(item.get("location"), dict)
                or not isinstance(item["location"].get("file"), str)
                for item in report_data
            ):
                raise ValueError("expected a list of deptry findings")
            if result.returncode == 1 and not report_data:
                raise ValueError("deptry failed without findings")
            return report_data
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"deptry report is not valid JSON: {exc}") from exc


def evidence_present(root: Path, tool: ToolOnly, files: list[str]) -> bool:
    """True when the evidence file is tracked and still matches the pattern."""
    if tool.evidence_file not in files:
        return False
    target = root / tool.evidence_file
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return re.search(tool.evidence_pattern, text, re.MULTILINE) is not None


def _fixture_for(manifest: Manifest, module: str, relative: str) -> FixtureModule | None:
    return next(
        (f for f in manifest.fixture_modules if f.module == module and f.covers(relative)), None
    )


def _stale_exemption(manifest: Manifest, module: str, message: str) -> Finding:
    return Finding(manifest.path, "STALE-EXEMPTION", module, str(DEFAULT_POLICY), message)


def _stale_fixtures(manifest: Manifest, used: set[FixtureModule]) -> list[Finding]:
    return [
        _stale_exemption(
            manifest,
            fixture.module,
            f"fixture_module matches no DEP001 finding in {fixture.used_in}; delete the entry",
        )
        for fixture in manifest.fixture_modules
        if fixture not in used
    ]


def _unused_finding(
    manifest: Manifest, module: str, where: str, tool: ToolOnly | None, root: Path, files: list[str]
) -> Finding | None:
    if tool is None:
        return Finding(
            manifest.path,
            "DEP002",
            module,
            where,
            "declared but never imported; remove it, or list it under tool_only "
            "with a reason and evidence if a CLI or plugin uses it",
        )
    if evidence_present(root, tool, files):
        return None
    return Finding(
        manifest.path,
        "STALE-EXEMPTION",
        module,
        where,
        f"tool-only exemption lost its evidence ({tool.evidence_file} no "
        f"longer matches {tool.evidence_pattern!r}); remove the dependency "
        "or restore the use",
    )


def _stale_transitives(
    manifest: Manifest,
    transitive: dict[str, TransitiveOk],
    declared: set[str],
    used: set[str],
    findings: list[Finding],
) -> list[Finding]:
    stale = []
    for module, entry in transitive.items():
        if entry.via not in declared:
            message = (
                f"transitive_ok relies on '{entry.via}', which the manifest no longer declares"
            )
        elif module not in used and not any(
            f.code == "DEP003" and f.module == module for f in findings
        ):
            message = "transitive_ok entry no longer matches any DEP003 finding; delete it"
        else:
            continue
        stale.append(_stale_exemption(manifest, module, message))
    return stale


def evaluate(
    manifest: Manifest,
    raw_findings: list[dict[str, Any]],
    root: Path,
    files: list[str],
    declared: set[str] | None = None,
    base: Path | None = None,
) -> list[Finding]:
    """Turn raw deptry findings into policy-filtered findings.

    ``base`` is the directory deptry ran in; its relative file paths resolve
    against it (default: ``root``).
    """
    findings: list[Finding] = []
    used_fixtures: set[FixtureModule] = set()
    exempt = {normalize(t.package): t for t in manifest.tool_only}
    reported_unused: set[str] = set()
    transitive = {t.module: t for t in manifest.transitive_ok}
    used_transitive: set[str] = set()
    declared = declared if declared is not None else set()

    for item in raw_findings:
        code = item["error"]["code"]
        module = item["module"]
        location = item["location"]
        where = f"{location['file']}:{location.get('line') or 0}"
        if code == "DEP002":
            package = normalize(module)
            reported_unused.add(package)
            unused = _unused_finding(manifest, module, where, exempt.get(package), root, files)
            if unused is not None:
                findings.append(unused)
            continue
        relative = _relative(location["file"], root, base)
        if code == "DEP003" and module in transitive:
            entry = transitive[module]
            if relative.startswith(entry.only_under) and entry.via in declared:
                used_transitive.add(module)
                continue
        if code == "DEP001" and (fixture := _fixture_for(manifest, module, relative)):
            used_fixtures.add(fixture)
            continue
        findings.append(Finding(manifest.path, code, module, where, item["error"]["message"]))

    findings.extend(_stale_transitives(manifest, transitive, declared, used_transitive, findings))
    findings.extend(_stale_fixtures(manifest, used_fixtures))

    for package, tool in exempt.items():
        if package not in reported_unused:
            findings.append(
                _stale_exemption(
                    manifest,
                    tool.package,
                    "listed under tool_only but deptry no longer reports it unused "
                    "(removed from the manifest, or now imported); delete the exemption",
                )
            )
    return findings


def _relative(file: str, root: Path, base: Path | None = None) -> str:
    path = Path(file)
    if not path.is_absolute():
        path = (base or root) / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file


def check_manifest(manifest: Manifest, root: Path, files: list[str]) -> tuple[list[Finding], int]:
    manifest_dir = root if manifest.path in ("", ".") else root / manifest.path
    pyproject = manifest_dir / "pyproject.toml"
    if not pyproject.is_file():
        raise PolicyError(f"manifest not found: {pyproject}")
    packages = declared_packages(pyproject)
    third_party = module_names_for(packages, manifest.module_map)
    third_party |= installed_third_party_modules(project_name(pyproject))
    first_party = first_party_names(files, manifest.path, third_party)
    raw = run_deptry(manifest_dir, deptry_args(manifest, first_party))
    return evaluate(manifest, raw, root, files, packages, manifest_dir), len(packages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--policy", type=Path, default=None, help="policy TOML path")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    policy_path = args.policy or (root / DEFAULT_POLICY)
    try:
        manifests = load_policy(policy_path)
        files = tracked_files(root)
        all_findings: list[Finding] = []
        examined = 0
        for manifest in manifests:
            findings, count = check_manifest(manifest, root, files)
            all_findings.extend(findings)
            examined += count
    except PolicyError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except RuntimeError as exc:
        print(f"EXTERNAL ERROR: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    for finding in all_findings:
        print(finding.render())
    print(
        f"dependency usage: {examined} declared packages across {len(manifests)} manifests, "
        f"{len(all_findings)} findings"
    )
    return EXIT_LOGIC if all_findings else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
