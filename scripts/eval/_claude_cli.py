"""Claude Code CLI transport: the claude/subscription cell of the matrix.

Sibling of `_copilot_cli`, same job, different binary. `_providers`
`resolve_provider("claude-cli")` is the supported entry point; import the
class directly only from tests.

What this transport is for, and what it is not: it answers "does this change
help the Claude models I already pay a seat for", by driving the binary the
operator's own sessions run in. It is not the claude/api cell. That cell is
the urllib path in `_anthropic_api` and stays where it is, because every
checked-in baseline was measured there and moving it would move them.

## Billing is the whole point, so it is enforced, not assumed

Claude Code's documented credential precedence puts the metered credentials
above the subscription one: cloud-provider variables, then
`ANTHROPIC_AUTH_TOKEN`, then `ANTHROPIC_API_KEY`, then `apiKeyHelper`, and
only then `CLAUDE_CODE_OAUTH_TOKEN` and an interactive login
(https://code.claude.com/docs/en/iam, read 2026-09-16). The same page is
explicit about the non-interactive case: in `--print` mode the API key is
always used when present. An operator with a key exported would therefore get
an API-billed run out of the subscription column, and nothing in the report
would say so.

So `ANTHROPIC_API_KEY` and the cloud-provider switches are removed from the
child environment, and `--setting-sources ""` drops the settings files an
`apiKeyHelper` could come from.

## The environment is inherited, minus what breaks the cell

The eval cell's child gets the parent environment, not an allowlist, so a
proxy, a CA bundle, or a gateway the operator exported reaches it. (The skill
harness calls `_build_env(..., inherit=False)` and gets the allowlist instead,
because its child loads the skill under test with slash commands on.) Only
these are denied:

- every `CLAUDE*` name (`_ISOLATION_DENY_PREFIXES`): `CLAUDE_CONFIG_DIR`, the
  parent session's `CLAUDECODE` and `CLAUDE_CODE_*` plumbing, and the
  `CLAUDE_CODE_USE_*` cloud switches. The transport sets back what it needs.
- `ANTHROPIC_API_KEY` (`_BLOCKED_BILLING_ENV`): it would make the cell
  API-billed under a subscription label.
- `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, and `ANTHROPIC_CUSTOM_HEADERS`
  on every step except `gateway`. The token outranks the OAuth token, and a
  custom header can carry an `Authorization` or `x-api-key` value, so either
  could authenticate a run that records a different credential. A base URL
  alone would send the OAuth seat token to that host.

## Gateway

`ANTHROPIC_BASE_URL` plus `ANTHROPIC_AUTH_TOKEN` is the gateway pair (a local
CLIProxy hub, for example). Because Claude Code ranks the auth token above
`CLAUDE_CODE_OAUTH_TOKEN`, the gateway is what authenticates whenever the pair
is set. So it is resolved first, recorded as `gateway`, and no OAuth token is
injected next to it. The gateway decides which account pays, so a `gateway`
run is not a direct subscription run: `endpoint_host` names the host it
reached, and `_transport_record` writes it into `eval-prompt-change.py`
results (other runners do not write it yet).
Neither the token nor the URL path is recorded. `_claude_gateway` owns the pair.

The base URL and the auth token reach the child only as a pair. A base URL
exported without the token is stripped, so the OAuth token on the other steps
only ever goes to api.anthropic.com.

## Isolation

`CLAUDE_CONFIG_DIR` relocates every `~/.claude` path, credentials included
(https://code.claude.com/docs/en/claude-directory, read 2026-09-16). Pointing
it at a fresh directory is what keeps user-level CLAUDE.md, settings, and
plugins out of a cell whose subject is usually those very files, and it is
also why the OAuth steps need an injected token: a relocated config directory
has no stored login in it. That is a deliberate trade, the same one
`eval_runtime_parity.py` already makes. Credential order and its steps live in
`_cli_credentials`. The `gateway` step also relocates but injects no token,
because the pair authenticates. Only the `existing-login` step skips the
relocation, so user config may load there; the run records that step.
The `EVAL_RUNTIME_REAL_HOME` opt-in also skips the relocation and reads no
credential file: it forwards an exported token or uses the CLI's own login.

Working directory is a fresh empty temporary directory, so the repository's
own `CLAUDE.md` and `AGENTS.md` cannot leak into the cell. Tools and MCP are
off. What no flag removes is the CLI's own system prompt, which is constant
within a run: the same control argument ADR-058 makes, and the same reason
not to compare a `claude-cli` score against an HTTP provider's.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from _claude_gateway import (
    AUTH_TOKEN_ENV,
    BASE_URL_ENV,
    gateway_configured,
    gateway_preempt,
)
from _cli_credential_sources import claude_disk_token, claude_login_probe
from _cli_credentials import (
    STEP_ENV,
    STEP_EXISTING_LOGIN,
    STEP_GATEWAY,
    CredentialSpec,
    ResolvedCredential,
    remember_resolution,
    resolve_cached,
)
from _cli_transport import (
    BASE_ENV_ALLOWLIST,
    build_envelope,
    inherited_process_env,
    minimal_process_env,
    run_cli,
    validate_timeout,
)

__all__ = ["_ClaudeCLIProvider"]

PROVIDER_LABEL = "Claude CLI"

#: The subscription credential this cell runs on.
OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"

#: The metered key that would silently move the run onto API billing. Removed
#: from the child environment; the module docstring gives the precedence that
#: puts it above the subscription token. The cloud switches
#: (`CLAUDE_CODE_USE_BEDROCK` and its siblings) are covered by the prefix deny.
_BLOCKED_BILLING_ENV = frozenset({"ANTHROPIC_API_KEY"})

#: Names that may carry a credential other than the one a non-gateway step
#: records. They reach the child only on the `gateway` step.
_GATEWAY_ONLY_ENV = frozenset({BASE_URL_ENV, AUTH_TOKEN_ENV, "ANTHROPIC_CUSTOM_HEADERS"})

#: Every `CLAUDE*` name: the config directory, the parent session's plumbing,
#: and the cloud switches. The transport sets back the one it needs.
_ISOLATION_DENY_PREFIXES = ("CLAUDE",)

_MISSING_CREDENTIAL_MESSAGE = (
    f"{PROVIDER_LABEL} found no subscription credential. Tried, in order: "
    f"a gateway ({BASE_URL_ENV} plus {AUTH_TOKEN_ENV}), "
    f"{OAUTH_TOKEN_ENV} in the environment or a dotenv file (EVAL_DOTENV_FILES), "
    "the token Claude Code stored under its config directory, the CLI's own "
    "claude.ai login, and a prompt (stdin is not a terminal). Export the "
    f"gateway pair, run `claude setup-token` and export the result as "
    f"{OAUTH_TOKEN_ENV}, run `claude auth login`, or select the claude-api "
    "cell to run on ANTHROPIC_API_KEY instead."
)


#: Variability for the shared credential order in `_cli_credentials`.
CREDENTIAL_SPEC = CredentialSpec(
    transport="claude-cli",
    env_names=(OAUTH_TOKEN_ENV,),
    inject_env=OAUTH_TOKEN_ENV,
    read_disk=claude_disk_token,
    login_probe=claude_login_probe,
    missing_message=_MISSING_CREDENTIAL_MESSAGE,
    preempt=gateway_preempt,
)

#: Same variable `eval_runtime_parity.py --real-home` sets (issue #5404). Under
#: it the CLI runs on the operator's own HOME, so it finds its own stored
#: login and loads `~/.claude` instructions ambiently. Off by default.
REAL_HOME_ENV = "EVAL_RUNTIME_REAL_HOME"


def _real_home_requested() -> bool:
    return os.environ.get(REAL_HOME_ENV) == "1"


#: Every built-in that can touch the filesystem, the network, a shell, or
#: another agent. A text eval needs none of them, and each one that stays
#: enabled is tool schema occupying the context the eval is measuring.
_DISALLOWED_TOOLS = (
    "Agent Bash BashOutput Edit Glob Grep KillShell NotebookEdit Read "
    "SlashCommand Task TodoWrite WebFetch WebSearch Write mcp__*"
)

#: An empty MCP configuration plus --strict-mcp-config means no server is
#: started, whatever the operator has configured elsewhere.
_EMPTY_MCP_CONFIG = json.dumps({"mcpServers": {}}, separators=(",", ":"))


class _ClaudeCLIProvider:
    """Claude Code CLI driven as a one-shot `--print` subprocess."""

    name = "claude-cli"

    def __init__(self, *, executable: str = "claude", timeout: float = 900.0) -> None:
        self._executable = executable
        self._timeout = validate_timeout(timeout)
        self._provider_label = PROVIDER_LABEL
        self.system_fingerprint: str | None = None
        #: `usage.output_tokens` from the last reply's envelope, or None when
        #: the envelope carried no usable count. Includes thinking tokens, as
        #: the Messages API count does. Never defaults to 0 (see `_read_output_tokens`).
        self.output_tokens: int | None = None
        self.credential_step: str | None = None

    def _build_argv(self, model: str) -> list[str]:
        """Build the fixed, shell-free Claude Code CLI invocation."""
        return [
            self._executable,
            "--print",
            "--output-format",
            "json",
            "--model",
            model,
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--mcp-config",
            _EMPTY_MCP_CONFIG,
            # `--tools ""` turns every built-in off, including any a later CLI
            # adds. The named deny list stays as a backstop.
            "--tools",
            "",
            "--disallowed-tools",
            _DISALLOWED_TOOLS,
            "--disable-slash-commands",
            "--no-session-persistence",
        ]

    def _build_env(
        self, config_dir: Path, credential: ResolvedCredential, *, inherit: bool = True
    ) -> dict[str, str]:
        """Build the child environment for the resolved credential step.

        With `inherit` (the eval cell), the parent environment is inherited
        minus the deny list in the module docstring. Without it (the skill
        harness, whose child loads the skill under test with slash commands
        on), the child gets only `BASE_ENV_ALLOWLIST`, plus `_GATEWAY_ONLY_ENV`
        (the pair and `ANTHROPIC_CUSTOM_HEADERS`) on the `gateway` step, so no
        other parent secret can reach it.

        An injected token and the `gateway` step run under a relocated, empty
        config directory. The `existing-login` step instead
        forwards the operator's config directory, because that is where its
        login lives. Under the real-HOME opt-in no config directory is set.

        `_GATEWAY_ONLY_ENV` reaches the child only on the `gateway` step. On
        any other step it could outrank the credential the run records.
        """
        gateway = credential.step == STEP_GATEWAY
        if gateway and not gateway_configured(os.environ):
            # The step is cached for the process; the pair has since changed.
            raise RuntimeError(
                f"{PROVIDER_LABEL} resolved a gateway, but {BASE_URL_ENV} or "
                f"{AUTH_TOKEN_ENV} is no longer set. Rerun with both exported."
            )
        denied = set(_BLOCKED_BILLING_ENV)
        if not gateway:
            denied |= _GATEWAY_ONLY_ENV
        overrides: dict[str, str] = {}
        if credential.secret is not None:
            overrides[OAUTH_TOKEN_ENV] = credential.secret
        # Under the real-HOME opt-in the CLI runs on the operator's own HOME
        # with no relocated config and finds its own login. Nothing is linked,
        # copied, or read here, and no config directory is set.
        if not _real_home_requested():
            if credential.secret is not None or gateway:
                overrides["CLAUDE_CONFIG_DIR"] = str(config_dir)
            elif forwarded := os.environ.get("CLAUDE_CONFIG_DIR"):
                overrides["CLAUDE_CONFIG_DIR"] = forwarded
        # `_cli_transport` is a flat sibling module, so mypy resolves it to Any
        # under `ignore_missing_imports`. Pin the contract at this boundary
        # rather than letting Any leak into the subprocess call.
        env: dict[str, str]
        if inherit:
            env = inherited_process_env(
                denied_names=frozenset(denied),
                denied_prefixes=_ISOLATION_DENY_PREFIXES,
                overrides=overrides,
            )
        else:
            allow = BASE_ENV_ALLOWLIST | (_GATEWAY_ONLY_ENV if gateway else frozenset())
            env = minimal_process_env(allow=allow, blocked=frozenset(denied), overrides=overrides)
        return env

    @staticmethod
    def _resolve_credential(executable: str) -> ResolvedCredential:
        """Walk the shared credential order, or the real-HOME subset.

        Under the real-HOME opt-in no credential file or dotenv FIFO is read:
        an exported gateway pair wins, as it does in the CLI, then an exported
        token is forwarded, else the CLI uses its own login.
        """
        if not _real_home_requested():
            return resolve_cached(CREDENTIAL_SPEC, executable=executable)
        if (preempted := gateway_preempt(os.environ)) is not None:
            resolved = preempted
        elif token := os.environ.get(OAUTH_TOKEN_ENV):
            resolved = ResolvedCredential(STEP_ENV, token)
        else:
            resolved = ResolvedCredential(STEP_EXISTING_LOGIN)
        remember_resolution(f"{CREDENTIAL_SPEC.transport}-real-home", resolved)
        return resolved

    def _read_answer(self, stdout: str, model: str) -> tuple[str, str | None]:
        """Return answer text and the model the CLI reported answering with.

        `--output-format json` is used rather than `text` precisely so this
        can be read: the `modelUsage` keys are the CLI's own record of which
        model served the turn, so a run cannot score an unrequested model
        without the mismatch surfacing here.
        """
        try:
            payload = json.loads(stdout)
        except (TypeError, ValueError):
            raise RuntimeError(
                f"{PROVIDER_LABEL} returned output that is not the JSON "
                "envelope --output-format json promises; response redacted"
            ) from None
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"{PROVIDER_LABEL} returned a JSON value that is not an object; response redacted"
            )
        if payload.get("is_error"):
            raise RuntimeError(
                f"{PROVIDER_LABEL} reported an error result: "
                f"error={payload.get('subtype') or 'unknown'}; "
                "response redacted"
            )
        answer = payload.get("result")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(
                f"{PROVIDER_LABEL} API returned no choices; model identifier redacted"
            )
        model_used = self._confirm_model(payload, model)
        self.output_tokens = self._read_output_tokens(payload)
        return answer, model_used

    @staticmethod
    def _read_output_tokens(payload: dict[str, Any]) -> int | None:
        """Return the envelope's `usage.output_tokens`, or None when unusable.

        The answer text alone gives a concision control no token count (#6683).
        Measured 2026-10-18 against `--output-format json`: the top-level
        `usage` object carries `output_tokens`, and it counts thinking tokens
        (`output_tokens_details.thinking_tokens`) along with the visible reply,
        so a one-line answer can report dozens of tokens. That matches what
        the Messages API reports, so the two stay comparable.

        A missing, non-integer, boolean, or negative value is None, never 0:
        a zero would read as a measured empty reply. `bool` is an `int`
        subclass, so it is refused by name.
        """
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None
        tokens = usage.get("output_tokens")
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            return None
        return tokens

    def _confirm_model(self, payload: dict[str, Any], model: str) -> str | None:
        """Return the served model id, or raise when it is not the one asked for.

        None means the envelope carried no usage record to check against. That
        is reported rather than treated as agreement, the same way the Copilot
        transport reports an unreadable transcript.

        `modelUsage` can carry more than one key for a single turn. Measured
        2026-09-16 against CLI 2.1.273: `--model claude-haiku-4-5-20251001`
        produced one key, and `--model claude-haiku-4-5` produced two, the
        alias and the dated id it resolved to. So the check is that *every*
        key belongs to the requested family, not that there is exactly one.
        Requiring one would have failed every run made with an alias, and
        ignoring the extras would have let a second, unrequested model bill a
        turn without the report saying so.
        """
        usage = payload.get("modelUsage")
        if not isinstance(usage, dict) or not usage:
            return None
        served = sorted((str(key) for key in usage), key=len, reverse=True)
        if not all(self._model_matches(key, model) for key in served):
            raise RuntimeError(
                f"{PROVIDER_LABEL} model attribution mismatch; model identifiers redacted"
            )
        # The longest id is the most specific one the CLI resolved, which is
        # what an archived run should record rather than the alias typed in.
        return served[0]

    @staticmethod
    def _model_matches(served: str, requested: str) -> bool:
        """Accept a served id that resolves the requested one.

        `--model` takes an alias or a partial id and the CLI answers with the
        dated id it resolved to, so an equality check would reject every
        legitimate run made with an alias. Prefix matching in either direction
        is the narrowest rule that accepts `claude-haiku-4-5` against
        `claude-haiku-4-5-20251001` and still rejects a different family.
        """
        return served.startswith(requested) or requested.startswith(served)

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float | None = 0.0,
        seed: int | None = None,
    ) -> str:
        # The CLI exposes no sampling controls, so these are discarded rather
        # than silently ignored further down. A fixture that needs sampling
        # determinism belongs on an HTTP provider.
        del max_tokens, temperature, seed

        # Reset before anything can raise, so a failed call keeps no count
        # from the call before it.
        self.output_tokens = None
        prompt = build_envelope(PROVIDER_LABEL, messages, system)
        self.system_fingerprint = None
        with tempfile.TemporaryDirectory(prefix="eval-claude-cli-") as profile:
            credential = self._resolve_credential(self._executable)
            self.credential_step = credential.step
            env = self._build_env(Path(profile), credential)
            completed = run_cli(
                self._build_argv(model),
                prompt,
                provider_label=PROVIDER_LABEL,
                env=env,
                timeout=self._timeout,
            )
        answer, model_used = self._read_answer(completed.stdout, model)
        # None records that nobody confirmed, which is how an archived run
        # tells a confirmed answer apart from an unconfirmed one.
        self.system_fingerprint = model_used
        return answer
