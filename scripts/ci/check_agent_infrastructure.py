#!/usr/bin/env python3
"""Probe the agent infrastructure a workflow run depends on.

Extracted from ``.github/actions/check-agent-infrastructure/action.yml`` under
ADR-006 (no logic in workflow YAML). Issue #3527.

The composite action this replaces answers one question: can agent workflows
run here? It probes three things and grades them:

* ``ready``: the GitHub CLI is present, Copilot CLI is reachable, and the
  Copilot credential was accepted by GitHub.
* ``degraded``: reviews can still be attempted, but the Copilot credential
  could not be confirmed (rate limit or transport fault, not a refusal).
* ``unavailable``: reviews cannot run, so the caller must skip them.

Every probe is advisory. A missing tool produces a warning annotation and a
summary line, never a non-zero exit, because the caller decides what to do
with a degraded environment. Copilot is reached either as its own binary or
as a ``gh`` extension, and both spellings count.

Which credential this probes (issue #4778)
------------------------------------------
The auth probe targets ``COPILOT_GITHUB_TOKEN``, the credential the model
invocation actually presents, NOT the runner-scoped ``github.token`` used for
repository API reads.

Before issue #4778 the probe ran ``gh api user`` under the ambient ``GH_TOKEN``.
PR #4648 pointed that variable at the runner installation token, and an Actions
installation token can never resolve ``/user``: GitHub answers
``Resource not accessible by integration`` (HTTP 403). The probe therefore
reported ``Authentication: FAILED`` on every run while the credential the
reviewers needed went unchecked.

``gh api user`` is the faithful mirror of the Copilot CLI's own auth gate. The
CLI resolves the PAT user login from that same ``/user`` endpoint and reports
its refusal as, verbatim from issue #4778 run 31283819979 job 93169277989:

    Failed to fetch PAT user login (401): GitHub returned: Bad credentials

``tests/e2e/copilot_hook_probe.py`` is the canonical classifier for that output
and anchors rejection on exactly one marker::

    COPILOT_AUTH_REJECTED_MARKERS = ("github returned: bad credentials",)

Stricter/looser/different than canonical
----------------------------------------
This module classifies the ``gh`` transport rather than the Copilot CLI stderr,
so it delegates to ``scripts.github_core.api.classify_gh_failure_text`` instead
of restating ``copilot_hook_probe``'s marker lists. The mapping is:

* ``INVALID_CREDENTIALS`` -> ``REJECTED`` (matches ``copilot_auth_rejected``)
* ``RATE_LIMITED``, ``SECONDARY_RATE_LIMITED``, ``TRANSIENT_ERROR`` ->
  ``UNVERIFIED`` (matches ``copilot_transient_failure``: credential status is
  unknown, so do not send an operator to rotate a working secret)
* an empty or unset token -> ``ABSENT`` (matches ``copilot_auth_absent``)

``UNVERIFIED`` deliberately does NOT block reviews. A refusal is positive
evidence the credential is dead; a rate limit or a socket reset is not, and
blocking on it would turn a GitHub blip into a repository-wide review outage.

Raw ``gh`` output is never echoed. Only the classification reaches the log, so a
credential cannot leak into a public Actions transcript (CWE-532).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The composite action runs this file with bare ``python3``, so the ambient
# interpreter has nothing installed. ``scripts.github_core.api`` and everything
# it imports are stdlib-only; keep it that way or this step dies at module load.
from scripts.github_core.api import (  # noqa: E402
    GhAuthStatus,
    classify_gh_failure_text,
)

_READY = "ready"
_DEGRADED = "degraded"
_UNAVAILABLE = "unavailable"
# A GITHUB_OUTPUT heredoc delimiter must not appear in the value it wraps.
_DELIMITER = "EOF_SUMMARY"

COPILOT_TOKEN_ENV = "COPILOT_GITHUB_TOKEN"


class CopilotAuthStatus(Enum):
    """Why the Copilot credential can or cannot be used, by operator action.

    Collapsing these to a bool is what issue #4778 punished: one ``FAILED`` line
    covered a token that was never provisioned, a token GitHub refused, and a
    probe that never got an answer. Each needs a different response.
    """

    VALID = "valid"
    ABSENT = "absent"
    REJECTED = "rejected"
    UNVERIFIED = "unverified"


# Statuses that are positive evidence reviews cannot succeed. UNVERIFIED is
# absent from this set on purpose: see the module docstring.
_BLOCKING_AUTH_STATUSES = frozenset(
    {CopilotAuthStatus.ABSENT, CopilotAuthStatus.REJECTED}
)

_TRANSIENT_GH_STATUSES = frozenset(
    {
        GhAuthStatus.RATE_LIMITED,
        GhAuthStatus.SECONDARY_RATE_LIMITED,
        GhAuthStatus.TRANSIENT_ERROR,
    }
)

_AUTH_ANNOTATIONS: dict[CopilotAuthStatus, str] = {
    CopilotAuthStatus.ABSENT: (
        f"::warning::{COPILOT_TOKEN_ENV} is not set. Agent reviews cannot "
        "authenticate. Provision the secret in Repository Settings > Secrets."
    ),
    CopilotAuthStatus.REJECTED: (
        f"::warning::GitHub refused {COPILOT_TOKEN_ENV} (expired, revoked, or "
        "wrong scope). Rotate the secret; retrying will not help."
    ),
    CopilotAuthStatus.UNVERIFIED: (
        f"::warning::{COPILOT_TOKEN_ENV} could not be verified (rate limit or "
        "transport fault). Credential status is unknown; do not rotate on this."
    ),
}

_AUTH_SUMMARIES: dict[CopilotAuthStatus, str] = {
    CopilotAuthStatus.ABSENT: f"Copilot auth: ABSENT ({COPILOT_TOKEN_ENV} is empty)",
    CopilotAuthStatus.REJECTED: "Copilot auth: REJECTED (GitHub refused the credential)",
    CopilotAuthStatus.UNVERIFIED: "Copilot auth: UNVERIFIED (rate limit or transport fault)",
}


@dataclass
class Probe:
    """The outcome of probing the agent toolchain."""

    github_cli: bool = False
    copilot: bool = False
    copilot_auth: CopilotAuthStatus = CopilotAuthStatus.UNVERIFIED
    summary: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)

    @property
    def auth_valid(self) -> bool:
        """Whether GitHub accepted the credential the reviewers will present."""
        return self.copilot_auth is CopilotAuthStatus.VALID

    @property
    def reviews_enabled(self) -> bool:
        """Whether the caller should launch agent review jobs.

        The single gating output. False only on positive evidence: a missing
        tool, or a credential GitHub refused or that was never provisioned.
        """
        return (
            self.github_cli
            and self.copilot
            and self.copilot_auth not in _BLOCKING_AUTH_STATUSES
        )

    @property
    def status(self) -> str:
        """Grade the environment the way the caller's ``if`` conditions expect."""
        if not self.reviews_enabled:
            return _UNAVAILABLE
        return _READY if self.auth_valid else _DEGRADED


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """A completed probe command, with its output kept out of the log."""

    returncode: int
    output: str


def _run(argv: list[str], env: dict[str, str] | None = None) -> CommandOutcome:
    """Run a probe command, merging its streams and never raising."""
    sys.stdout.flush()
    try:
        completed = subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:  # missing binary, or exec refused by the OS
        return CommandOutcome(returncode=127, output=str(exc))
    return CommandOutcome(returncode=completed.returncode, output=completed.stdout)


def _first_line(argv: list[str]) -> str | None:
    """Return the first line of a command's output, or None when it fails."""
    outcome = _run(argv)
    if outcome.returncode != 0:
        return None
    lines = outcome.output.splitlines()
    return lines[0] if lines else ""


def _probe_github_cli(probe: Probe) -> None:
    if shutil.which("gh") is None:
        probe.summary.append("GitHub CLI: NOT FOUND")
        probe.annotations.append("::warning::GitHub CLI not found. Agent workflows require gh.")
        return
    probe.github_cli = True
    version = _first_line(["gh", "--version"]) or "unknown"
    probe.summary.append(f"GitHub CLI: {version}")
    probe.annotations.append(f"::notice::GitHub CLI available ({version})")


def _copilot_token_environment(token: str) -> dict[str, str]:
    """Environment that forces ``gh`` onto the Copilot credential.

    ``gh`` prefers ``GH_TOKEN`` over ``GITHUB_TOKEN``; both are overridden so an
    ambient runner installation token cannot answer for the credential under
    test, which is the exact substitution that produced issue #4778.
    """
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    env["GITHUB_TOKEN"] = token
    return env


def classify_copilot_auth(outcome: CommandOutcome) -> CopilotAuthStatus:
    """Map a ``gh api user`` outcome to the operator action it requires."""
    if outcome.returncode == 0:
        return CopilotAuthStatus.VALID
    if classify_gh_failure_text(outcome.output) in _TRANSIENT_GH_STATUSES:
        return CopilotAuthStatus.UNVERIFIED
    return CopilotAuthStatus.REJECTED


def _record_auth(probe: Probe, status: CopilotAuthStatus, login: str = "") -> None:
    """Record one auth outcome as a summary line plus one annotation."""
    probe.copilot_auth = status
    if status is CopilotAuthStatus.VALID:
        probe.summary.append(f"Copilot auth: valid (user: {login})")
        probe.annotations.append(f"::notice::Copilot credential accepted for {login}")
        return
    probe.summary.append(_AUTH_SUMMARIES[status])
    probe.annotations.append(_AUTH_ANNOTATIONS[status])


def _login_from(outcome: CommandOutcome) -> str:
    """First output line of a successful ``gh api user -q .login`` call."""
    lines = outcome.output.splitlines()
    return lines[0].strip() if lines and lines[0].strip() else "unknown"


def _probe_copilot_auth(probe: Probe) -> None:
    """Probe ``COPILOT_GITHUB_TOKEN`` against the endpoint the CLI itself uses."""
    token = os.environ.get(COPILOT_TOKEN_ENV, "").strip()
    if not token:
        _record_auth(probe, CopilotAuthStatus.ABSENT)
        return
    if not probe.github_cli:
        probe.copilot_auth = CopilotAuthStatus.UNVERIFIED
        probe.summary.append("Copilot auth: UNVERIFIED (no gh CLI to probe with)")
        return

    outcome = _run(
        ["gh", "api", "user", "-q", ".login"],
        env=_copilot_token_environment(token),
    )
    status = classify_copilot_auth(outcome)
    _record_auth(probe, status, _login_from(outcome))


def _probe_copilot(probe: Probe) -> None:
    if shutil.which("copilot") is not None:
        probe.copilot = True
        version = _first_line(["copilot", "--version"]) or "unknown"
        probe.summary.append(f"Copilot CLI: {version}")
        probe.annotations.append(f"::notice::Copilot CLI available ({version})")
        return
    if probe.github_cli:
        probed = _first_line(["gh", "copilot", "--version"])
        if probed is not None:
            probe.copilot = True
            version = probed or "unknown"
            probe.summary.append(f"Copilot CLI (via gh extension): {version}")
            probe.annotations.append(
                f"::notice::Copilot CLI available via gh extension ({version})"
            )
            return
    probe.summary.append("Copilot CLI: NOT FOUND")
    probe.annotations.append(
        "::warning::Copilot CLI binary not available. Install the standalone "
        "CLI or the gh copilot extension."
    )


def _record_gate(probe: Probe) -> None:
    """State plainly whether reviews will run, so the log cannot mislead.

    Issue #4778: the preflight announced "reviews will be skipped" while the
    caller gated on binary presence alone and launched all ten anyway.
    """
    if probe.reviews_enabled:
        probe.summary.append("Agent reviews: ENABLED")
        return
    probe.summary.append("Agent reviews: SKIPPED (infrastructure unavailable)")
    probe.annotations.append(
        "::warning::Agent reviews will be skipped. Each review records "
        "DID_NOT_RUN and AI Quality Gate Results blocks the merge."
    )


def run_probes() -> Probe:
    """Probe the toolchain and return the graded result."""
    probe = Probe()
    _probe_github_cli(probe)
    _probe_copilot(probe)
    _probe_copilot_auth(probe)
    _record_gate(probe)
    probe.summary.append(f"Overall: {probe.status}")
    return probe


def render_outputs(probe: Probe) -> str:
    """Render the step outputs, escaping any value that could close the heredoc."""
    summary = "\n".join(line.replace(_DELIMITER, _DELIMITER + "_ESCAPED") for line in probe.summary)
    return (
        f"github-cli-available={str(probe.github_cli).lower()}\n"
        f"copilot-available={str(probe.copilot).lower()}\n"
        f"copilot-auth-status={probe.copilot_auth.value}\n"
        f"auth-valid={str(probe.auth_valid).lower()}\n"
        f"reviews-enabled={str(probe.reviews_enabled).lower()}\n"
        f"overall-status={probe.status}\n"
        f"summary<<{_DELIMITER}\n{summary}\n{_DELIMITER}\n"
    )


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0]).parse_args(argv)

    probe = run_probes()
    for annotation in probe.annotations:
        print(annotation)

    print("")
    print("=== Infrastructure Health Check ===")
    for line in probe.summary:
        print(f"  {line}")
    print("==================================")

    body = render_outputs(probe)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(body, end="")
        return 0
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
