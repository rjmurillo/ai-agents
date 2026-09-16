"""Static guards over ``scripts/bootstrap-vm.sh``'s repo-script call sites.

The script provisions every remote container (Claude Code on the web calls it
from ``.claude/hooks/session-start.sh``). It runs under ``set -euo pipefail``,
so a single failing step takes every later step with it silently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VM_BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "bootstrap-vm.sh"


def _referenced_repo_scripts(script_text: str) -> list[str]:
    """Repo-relative script paths a bootstrap shell script hands to an interpreter.

    Matches only paths rooted at a first-party source directory, so absolute
    temp paths (``/tmp/ms.deb``) and bare tool names are ignored. Comment lines
    are skipped: a path named in prose is documentation, not a call site.
    """
    pattern = re.compile(r"\b((?:scripts|build|\.claude|src)/[\w./-]+\.(?:py|ps1|sh))")
    found: list[str] = []
    for line in script_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        found.extend(pattern.findall(stripped))
    return found


def test_vm_bootstrap_references_no_deleted_script() -> None:
    """Every repo script bootstrap-vm.sh invokes must still exist.

    The script runs under ``set -euo pipefail``, so one call to a deleted path
    exits it on the spot and every later step is skipped silently. ADR-089
    deleted ``scripts/maintenance/install_merge_drivers.py`` but left the
    bootstrap call site behind; remote containers then aborted right after the
    Lefthook step, shipping no markdownlint-cli2, no actionlint, and no
    yamllint. ``test_causal_tier_removed.py`` asserted the file stayed deleted
    and could not see the caller.
    """
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    missing = [rel for rel in _referenced_repo_scripts(text) if not (REPO_ROOT / rel).exists()]

    assert not missing, (
        "scripts/bootstrap-vm.sh invokes repo scripts that do not exist: "
        f"{missing}. Under `set -e` this aborts bootstrap and silently skips "
        "every later install step."
    )


def test_referenced_repo_scripts_detects_a_missing_path() -> None:
    """Negative control: the guard must fail on the exact shape of the bug."""
    script = 'uv run --frozen python scripts/maintenance/install_merge_drivers.py\n'

    assert _referenced_repo_scripts(script) == [
        "scripts/maintenance/install_merge_drivers.py"
    ]


def test_referenced_repo_scripts_ignores_comments_and_absolute_paths() -> None:
    """Edge: prose mentions and non-repo paths are not call sites."""
    script = "\n".join(
        [
            "# see scripts/maintenance/gone.py for history",
            "wget -q https://example.invalid/pkg.deb -O /tmp/ms.deb",
            "sh /tmp/installer.sh",
            "python3 scripts/ci/verify_code_env.py",
        ]
    )

    assert _referenced_repo_scripts(script) == ["scripts/ci/verify_code_env.py"]


def test_vm_bootstrap_installs_actionlint_and_yamllint() -> None:
    """The workflow and YAML linters CI enforces must be part of bootstrap.

    Both are pre-PR gate dependencies (``.github/workflows/yaml-lint.yml``,
    ``scripts/validation/checks_tooling.py``). A container without them fails
    the gate for a missing tool rather than a real finding.
    """
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert "actionlint" in text
    assert "uv tool install --quiet yamllint" in text
