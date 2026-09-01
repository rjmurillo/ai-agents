#!/usr/bin/env python3
# taste-lint: ignore naming -- a library imported by the drift-check hook,
# registered as a hook nowhere. The `invoke_` prefix marks a registered entry
# point; using it here would assert the opposite of what is true. Same
# reasoning as `plugin_hook_drift_model.py`.
"""Turn a scan outcome into the message the session actually sees.

Split from `invoke_plugin_hook_drift_check.py`, which owns finding installs and
comparing them. This module owns the last step, where a correct comparison can
still mislead:

- Drift has three directions (extras, missing, unreadable) that call for
  opposite responses, so the summary is keyed on which are actually present.
  Telling a reader whose install is missing a hook to hunt for a retired rule
  sends them after a guard that is not there.
- A pass that did not finish has to say so. Zero reports reads as "nothing is
  installed", which is a claim the check has not earned.
- Everything printed is bounded, because one install carrying hundreds of
  registrations must not crowd the rest of the session's context off the top.

Refs: issue #5085.
"""

from __future__ import annotations

from collections.abc import Sequence

from plugin_hook_drift_model import InstallReport
from plugin_hook_drift_safety import MAX_PATH_CHARS, path_token, sanitize_label

# Ceilings on what is rendered into session context. The model caps how much of
# a manifest is read and parsed; these cap how much of the result is printed,
# so one install carrying hundreds of registrations cannot crowd out the rest
# of the session's context. Every cut is stated in the message.
MAX_LINES_PER_DIRECTION = 20
MAX_REPORTED_INSTALLS = 10

def _capped(lines: Sequence[str], label: str, prefix: str) -> list[str]:
    """Render at most ``MAX_LINES_PER_DIRECTION`` entries, saying what was cut.

    Individual labels are already length-capped, but their count is not, and a
    manifest under the scanned trees can carry as many registrations as its
    author likes. Without a count ceiling one install could push everything
    else in the session's context off the top of the message.
    """
    shown = [f"  - {prefix}: {line}" for line in lines[:MAX_LINES_PER_DIRECTION]]
    hidden = len(lines) - len(shown)
    if hidden > 0:
        shown.append(f"  - ...and {hidden} more {label} not shown (output capped)")
    return shown


def _format_report(report: InstallReport) -> str:
    # The path is a directory name an attacker may have chosen, so the prose
    # carries an opaque token rather than the text. `main` prints the
    # token-to-path mapping to stderr for the human reading the hook log.
    lines = [f"- `{path_token(report.install_path)}` ({report.surface})"]
    if report.error:
        lines.append(f"  - unreadable: {sanitize_label(report.error, MAX_PATH_CHARS)}")
    lines.extend(_capped(report.only_in_install, "extra", "**only in this install**"))
    lines.extend(_capped(report.only_in_source, "missing", "missing from this install"))
    return "\n".join(lines)


# Drift comes in three directions and they call for opposite responses, so the
# summary is keyed on which are actually present. Telling a reader whose
# install is *missing* a hook to go hunt for a retired rule sends them after a
# guard that is not there.
_EXTRAS_GUIDANCE = (
    "A hook that blocks you from one of these paths is enforcing a rule that "
    "may no longer exist in the repository; check here before diagnosing it as "
    "live code. Update the install (`/plugin` for Claude Code) to clear it."
)
_MISSING_GUIDANCE = (
    "These installs are behind this checkout, so a guard you expect to run is "
    "not registered there at all. Update the install (`/plugin` for Claude "
    "Code) to pick the hooks up."
)
_ERROR_GUIDANCE = (
    "Their registrations were never compared, so neither a match nor drift is "
    "established for them. Reinstall to replace the manifest."
)
_MIXED_GUIDANCE = (
    "Each entry below names the direction. A registration only the install has "
    "may enforce a rule that no longer exists in the repository; one only this "
    "checkout has is missing from the install; an unreadable manifest was not "
    "compared at all. Update the install (`/plugin` for Claude Code)."
)

_DRIFT_SUMMARY: dict[tuple[str, ...], tuple[str, str]] = {
    ("extras",): ("register hooks this checkout does not", _EXTRAS_GUIDANCE),
    ("missing",): ("are missing hooks this checkout ships", _MISSING_GUIDANCE),
    ("error",): ("have a hook manifest this check could not read", _ERROR_GUIDANCE),
}
_MIXED_SUMMARY = ("diverge from this checkout's hook registrations", _MIXED_GUIDANCE)


def _drift_kinds(reports: Sequence[InstallReport]) -> tuple[str, ...]:
    """Which of extras, missing, and error are present across ``reports``."""
    present = (
        ("extras", any(report.only_in_install for report in reports)),
        ("missing", any(report.only_in_source for report in reports)),
        ("error", any(report.error for report in reports)),
    )
    return tuple(kind for kind, seen in present if seen)


def _incomplete_block(incomplete: Sequence[str]) -> str:
    """Cap what the rest of the message is allowed to claim, or add nothing.

    The heading stays cause-neutral. `incomplete` mixes walks that hit the
    directory bound with surfaces never searched at all because their source
    manifest could not be read, and naming the scan bound up front would send a
    reader whose source manifest is broken off to raise a limit that had
    nothing to do with it. Each entry carries its own reason instead.
    """
    if not incomplete:
        return ""
    reasons = "".join(f"\n- not compared: {entry}" for entry in incomplete)
    return (
        "\n\n**This result is not conclusive.** Part of this check did not run, "
        "so an installed copy may exist that was never compared. Each entry "
        f"below names its own reason.{reasons}"
    )


def format_message(
    reports: list[InstallReport], notes: list[str], incomplete: Sequence[str] = ()
) -> str:
    """Render the session-start message, stating the clean case explicitly."""
    header = "## Installed Plugin Hook Drift\n\n"
    drifted = [report for report in reports if report.has_drift]
    note_block = "".join(f"\n- note: {note}" for note in notes)
    incomplete_block = _incomplete_block(incomplete)

    if not reports:
        reached = " was reached" if incomplete else " found on disk"
        return (
            header
            + f"No installed copy of this repository's plugins{reached}."
            + note_block
            + incomplete_block
        )

    if not drifted:
        return (
            header
            + f"{len(reports)} installed copy/copies match this checkout's hook "
            + "registrations."
            + note_block
            + incomplete_block
        )

    summary, guidance = _DRIFT_SUMMARY.get(_drift_kinds(drifted), _MIXED_SUMMARY)
    rendered = drifted[:MAX_REPORTED_INSTALLS]
    body = "\n".join(_format_report(report) for report in rendered)
    if len(drifted) > len(rendered):
        body += (
            f"\n- ...and {len(drifted) - len(rendered)} more drifted install(s) "
            "not shown (output capped)"
        )
    return (
        header
        + f"**{len(drifted)} of {len(reports)} installed copy/copies {summary}.** "
        + guidance
        + note_block
        + incomplete_block
        + "\n\n"
        + body
    )
