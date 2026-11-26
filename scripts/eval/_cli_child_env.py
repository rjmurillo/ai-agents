"""Child environments for the CLI transports: allowlist or inherit-minus-deny.

`minimal_process_env` is the default-deny builder the Codex and Copilot cells
use. `inherited_process_env` is the inherit-by-default builder the Claude cell
uses. Both force the same few variables and apply overrides last.
`_cli_transport` re-exports both, so callers import them from there.
"""

from __future__ import annotations

import os

__all__ = ["inherited_process_env", "minimal_process_env"]


def minimal_process_env(
    *,
    allow: frozenset[str],
    blocked: frozenset[str],
    overrides: dict[str, str],
) -> dict[str, str]:
    """Build the child environment for one CLI run.

    `blocked` wins over `allow`. That ordering is the guard rail, not a
    detail: the API-billing credentials a subscription transport must not
    inherit are the same names its API-billed sibling puts in `allow`, and a
    future edit that adds one to both lists should fail closed.
    """
    env = {name: value for name in allow - blocked if (value := os.environ.get(name)) is not None}
    return _finish_child_env(env, overrides)


def _finish_child_env(env: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    """Apply the variables every CLI child gets, then the transport's overrides."""
    env.setdefault("PATH", os.defpath)
    env["NO_COLOR"] = "1"
    env["PYTHONUTF8"] = "1"
    env.update(overrides)
    return env


def inherited_process_env(
    *,
    denied_names: frozenset[str],
    denied_prefixes: tuple[str, ...],
    overrides: dict[str, str],
) -> dict[str, str]:
    """Build a child environment that inherits the parent minus a deny list.

    The opposite default to `minimal_process_env`: everything the operator
    exported reaches the child unless it is named in `denied_names` or starts
    with one of `denied_prefixes`. Use it where the only names that matter are
    the few that would break the cell, and stripping the rest only breaks the
    operator's own setup (a proxy, a gateway, a CA bundle). `overrides` apply
    last, so a transport can put back a value it denied by prefix.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in denied_names and not name.startswith(denied_prefixes)
    }
    return _finish_child_env(env, overrides)
