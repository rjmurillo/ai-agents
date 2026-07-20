"""Regression guard: markdownlint-cli2 stays version-pinned in CI config (Issue #3279).

Unpinned ``npm install --global markdownlint-cli2`` and ``npx markdownlint-cli2``
invocations float to whatever the registry serves that day. A silent major bump
can change lint rule defaults and red an otherwise-clean ``main``. This guard
scans the CI configuration surface (composite actions, workflows, and
``lefthook.yml`` when present) for *active* markdownlint-cli2 invocations and
asserts two invariants:

1. Every active invocation is pinned to an explicit ``@<version>``.
2. All pinned sites share a single version (one declarative owner). If two sites
   drift to different versions, the guard fails so the drift is caught in review
   rather than in a confusing runtime mismatch.

Scope note: only CI config files are scanned. Prose and comment *mentions*
(echoed strings, step names, ``# ...`` comments) are intentionally ignored,
because they are not invocations. The scanner keys off a package-runner token
(``npm install``/``npm i``/``npm exec``/``npx``/``pnpm add``/``yarn add``)
immediately preceding the binary, so ``echo "markdownlint-cli2 installed"`` and
``- name: Install markdownlint-cli2`` do not trip it.

The Python PreToolUse hook ``invoke_markdownlint_guard.py`` resolves the binary
at runtime via ``shutil.which`` with an ``npx`` fallback; it is deliberately not
scanned. It is dev-machine runtime resolution (transitively pinned by the global
install here), and it is on the hook-retirement path of epic #3197.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# A package-runner token immediately preceding the binary marks an *active*
# invocation (as opposed to a prose mention). The optional trailing group
# captures the ``@<version>`` pin when present; it stops at the first
# whitespace/quote so trailing args like ``--help`` are never swallowed.
_INVOCATION_RE = re.compile(
    r"(?:npm\s+(?:install|i|exec)|npx|pnpm\s+(?:add|dlx)|yarn\s+(?:add|dlx))"
    r"\b[^\n]*?\bmarkdownlint-cli2(?P<pin>@[^\s\"'`]+)?",
)


def _config_files() -> list[Path]:
    """CI config files that may carry a markdownlint-cli2 invocation.

    Composite actions, workflows, and the optional root lefthook config. The
    lefthook file lives on the lefthook-migration branch (#3259) and is absent on
    ``main``; it is included when present so the guard covers it once it lands.
    """
    files: list[Path] = []
    files.extend(sorted((REPO_ROOT / ".github" / "actions").rglob("action.yml")))
    files.extend(sorted((REPO_ROOT / ".github" / "actions").rglob("action.yaml")))
    files.extend(sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")))
    files.extend(sorted((REPO_ROOT / ".github" / "workflows").glob("*.yaml")))
    lefthook = REPO_ROOT / "lefthook.yml"
    if lefthook.is_file():
        files.append(lefthook)
    return files


def _detect(line: str) -> tuple[bool, str | None]:
    """Classify a single line.

    Returns ``(is_active_invocation, pinned_version_or_None)``. Comment lines
    (stripped form starting with ``#``) are never treated as invocations.
    """
    if line.lstrip().startswith("#"):
        return (False, None)
    match = _INVOCATION_RE.search(line)
    if match is None:
        return (False, None)
    pin = match.group("pin")
    version = pin[1:] if pin else None
    return (True, version)


def _scan() -> list[tuple[Path, int, str, str | None]]:
    """All active invocations across config files as (path, lineno, line, version)."""
    found: list[tuple[Path, int, str, str | None]] = []
    for path in _config_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            active, version = _detect(line)
            if active:
                found.append((path, lineno, line.strip(), version))
    return found


# --- Detector unit coverage (positive, negative, edge) -----------------------


def test_detects_pinned_npm_install() -> None:
    """A pinned global install is an active invocation with the version extracted."""
    active, version = _detect("        npm install --global markdownlint-cli2@0.23.1")
    assert active is True
    assert version == "0.23.1"


def test_detects_pinned_npx_with_trailing_args() -> None:
    """The pin stops at whitespace so trailing flags (``--help``) are not swallowed."""
    active, version = _detect("          $null = npx markdownlint-cli2@0.23.1 --help 2>&1")
    assert active is True
    assert version == "0.23.1"


def test_unpinned_npm_install_flagged() -> None:
    """An unpinned install is active but reports no version (the failure the guard catches)."""
    active, version = _detect("        npm install --global markdownlint-cli2")
    assert active is True
    assert version is None


def test_unpinned_npx_flagged() -> None:
    """An unpinned npx invocation is active with no version."""
    active, version = _detect("          $null = npx markdownlint-cli2 --help 2>&1")
    assert active is True
    assert version is None


def test_echo_mention_is_not_an_invocation() -> None:
    """A prose echo that names the tool is not an invocation."""
    active, version = _detect('        echo "Installing markdownlint-cli2..."')
    assert active is False
    assert version is None


def test_step_name_is_not_an_invocation() -> None:
    """A YAML step name mentioning the tool is not an invocation."""
    active, _ = _detect("    - name: Install markdownlint-cli2")
    assert active is False


def test_comment_line_is_not_an_invocation() -> None:
    """A comment referencing the tool is skipped even if it contains npx."""
    active, _ = _detect("          # Check if npx markdownlint-cli2 is available")
    assert active is False


def test_pnpm_and_yarn_forms_detected() -> None:
    """Alternate runners are recognized so a switch away from npm stays guarded."""
    active_pnpm, ver_pnpm = _detect("        pnpm add -g markdownlint-cli2@0.23.1")
    active_yarn, ver_yarn = _detect("        yarn dlx markdownlint-cli2@0.23.1 --help")
    assert (active_pnpm, ver_pnpm) == (True, "0.23.1")
    assert (active_yarn, ver_yarn) == (True, "0.23.1")


# --- Repo invariants (guard against vacuous pass, unpinned drift, split owners) ---


def test_scanner_finds_at_least_one_real_invocation() -> None:
    """Guard against a vacuous pass if a refactor moves or renames the invocation."""
    invocations = _scan()
    assert invocations, (
        "no active markdownlint-cli2 invocation found in CI config; "
        "the scanner or the invocation site moved. Update _config_files() or the regex."
    )


def test_all_repo_invocations_are_pinned() -> None:
    """Every active markdownlint-cli2 invocation in CI config carries an @version pin."""
    unpinned = [(str(p.relative_to(REPO_ROOT)), n, ln) for p, n, ln, v in _scan() if v is None]
    assert not unpinned, (
        "unpinned markdownlint-cli2 invocation(s) found; pin each to @<version>:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in unpinned)
    )


def test_single_pinned_version_across_all_sites() -> None:
    """All pinned sites share one version (single declarative owner)."""
    versions = {v for _, _, _, v in _scan() if v is not None}
    assert len(versions) <= 1, (
        f"markdownlint-cli2 pinned to multiple versions {sorted(versions)}; "
        "keep every site on one owned version."
    )
