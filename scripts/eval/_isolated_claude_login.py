"""Give an isolated Claude run the stored subscription login, as a token.

`runtime_env` stays login-free because capability probes share it. A deliberate
live run (the parity runner, the control ablation runner) resolves the
credential the way the `claude-cli` grader does and passes it as an environment
variable under the empty profile, which keeps `~/.claude` instructions out of
the run. No credential file is copied or linked.
"""

from __future__ import annotations

import os

import _claude_cli
from _cli_credentials import CredentialNotFoundError, resolve_cached
from _runtime_harness import credential_values

_NO_ISOLATED_LOGIN = (
    "an isolated Claude run needs a token, but the stored login has none. "
    "Run `claude setup-token` and export CLAUDE_CODE_OAUTH_TOKEN, or pass --real-home."
)
_API_KEY_ENV = "ANTHROPIC_API_KEY"


class IsolatedLoginError(RuntimeError):
    """No credential reaches an isolated Claude run."""


def add_claude_login(env: dict[str, str], executable: str) -> None:
    """Add the resolved token to `env`, or raise `IsolatedLoginError`.

    Blank credential variables are dropped first. An exported key or token wins
    over the stored login and is left alone.
    """
    spec = _claude_cli.CREDENTIAL_SPEC
    for name in (_API_KEY_ENV, spec.inject_env):
        if name in env and not env[name].strip():
            del env[name]
    if _API_KEY_ENV in env or spec.inject_env in env:
        return
    try:
        credential = resolve_cached(spec, executable=executable)
    except CredentialNotFoundError as exc:
        raise IsolatedLoginError(str(exc)) from exc
    if credential.secret is None:
        raise IsolatedLoginError(_NO_ISOLATED_LOGIN)
    env[spec.inject_env] = credential.secret


def require_isolated_login(executable: str) -> dict[str, str]:
    """Return the credential variables an isolated run will carry, or raise.

    Call before any workspace exists, so a missing login stops the run early.
    """
    names = (_API_KEY_ENV, _claude_cli.CREDENTIAL_SPEC.inject_env)
    env = {name: os.environ[name] for name in names if name in os.environ}
    add_claude_login(env, executable)
    return env


def isolated_login_values(executable: str, *, skip: bool) -> list[str]:
    """Resolve the login an isolated run needs and return its secret values.

    `skip` is true for runs that need none (dry run, `--real-home`). The values
    are what the child will carry, so a report can scrub them.
    """
    if skip:
        return []
    values: list[str] = credential_values("claude", require_isolated_login(executable))
    return values
