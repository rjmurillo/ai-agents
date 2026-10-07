"""Version pins for the tools ``scripts/bootstrap-vm.sh`` installs.

Every remote container runs the bootstrap. A floating install gives two
containers built a day apart different linters, so a gate can pass on one
and fail on the other.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VM_BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "bootstrap-vm.sh"
SETUP_CODE_ENV_PATH = REPO_ROOT / ".github" / "actions" / "setup-code-env" / "action.yml"


def _shell_assignment(script_text: str, name: str) -> str:
    """Value of a top-level ``NAME="value"`` assignment in a shell script."""
    match = re.search(rf'^{name}="([^"]+)"$', script_text, re.MULTILINE)
    assert match is not None, f"{name} is not assigned in bootstrap-vm.sh"
    return match.group(1)


def test_vm_bootstrap_pins_every_tool_version() -> None:
    """Each tool the bootstrap installs resolves to one exact release."""
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    for name in (
        "PESTER_VERSION",
        "POWERSHELL_YAML_VERSION",
        "MARKDOWNLINT_CLI2_VERSION",
        "YAMLLINT_VERSION",
    ):
        assert re.fullmatch(r"\d+\.\d+\.\d+", _shell_assignment(text, name)), name

    assert "-Name powershell-yaml -RequiredVersion $POWERSHELL_YAML_VERSION" in text
    assert "Where-Object Version -eq '$POWERSHELL_YAML_VERSION'" in text


# Each install command and the version variable its line must reference.
_INSTALL_PINS = (
    (re.compile(r"install -g\b.*markdownlint-cli2"), "MARKDOWNLINT_CLI2_VERSION"),
    (re.compile(r"uv tool install\b.*yamllint"), "YAMLLINT_VERSION"),
    (re.compile(r"Install-Module -Name Pester\b"), "PESTER_VERSION"),
    (re.compile(r"Install-Module -Name powershell-yaml\b"), "POWERSHELL_YAML_VERSION"),
)


def _floating_install_lines(script_text: str) -> list[str]:
    """Install lines that do not reference their tool's version variable."""
    offenders = []
    for line in script_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for command, variable in _INSTALL_PINS:
            if command.search(stripped) and not re.search(rf"\$\{{?{variable}\b", stripped):
                offenders.append(stripped)
    return offenders


def test_vm_bootstrap_has_no_floating_installs() -> None:
    """Every install line names its pinned version variable."""
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert _floating_install_lines(text) == []


def test_floating_install_guard_catches_unpinned_shapes() -> None:
    """Negative control: bare, quoted, and @latest installs are all flagged."""
    script = "\n".join(
        (
            '"$NPM_PATH" install -g markdownlint-cli2',
            '"$NPM_PATH" install -g "markdownlint-cli2"',
            '"$NPM_PATH" install -g markdownlint-cli2@latest',
            "uv tool install --quiet yamllint",
            "uv tool install --quiet --force 'yamllint>=1'",
            "Install-Module -Name powershell-yaml -Force -Scope CurrentUser",
            "Install-Module -Name Pester -Force",
        )
    )

    assert len(_floating_install_lines(script)) == 7


def test_vm_bootstrap_skip_checks_compare_pinned_version() -> None:
    """A warm container with another release reinstalls instead of skipping."""
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert '"markdownlint-cli2 v${MARKDOWNLINT_CLI2_VERSION} "' in text
    assert '"yamllint ${YAMLLINT_VERSION}"' in text
    assert "\nif markdownlint_cli2_pinned; then\n" in text
    assert "\nif yamllint_pinned; then\n" in text


def test_vm_bootstrap_markdownlint_matches_ci() -> None:
    """Containers and CI lint markdown with the same markdownlint-cli2 release."""
    pinned = _shell_assignment(
        VM_BOOTSTRAP_PATH.read_text(encoding="utf-8"), "MARKDOWNLINT_CLI2_VERSION"
    )
    action = SETUP_CODE_ENV_PATH.read_text(encoding="utf-8")

    assert f"markdownlint-cli2@{pinned}" in action
