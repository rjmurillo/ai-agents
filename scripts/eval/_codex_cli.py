"""Codex CLI transport: the codex/subscription cell of the matrix.

Sibling of `_claude_cli` and `_copilot_cli`. `_providers`
`resolve_provider("codex-cli")` is the supported entry point; import the class
directly only from tests.

This is the ChatGPT-plan half of the codex column. The other half, the
metered `OPENAI_API_KEY` one, is the existing OpenAI-compatible provider and
does not change.

## What is verified and what is not

Read from the `openai/codex` source on 2026-09-16 rather than from the doc
site, which redirects: `codex-rs/exec/src/cli.rs` declares the usage string
`codex exec [OPTIONS] [PROMPT]` and the `--json`, `--output-last-message`,
`--ephemeral`, and `--ignore-user-config` options;
`codex-rs/utils/cli/src/shared_options.rs` declares `-m/--model` and
`-s/--sandbox`. `CODEX_HOME`, `CODEX_API_KEY`, and `CODEX_ACCESS_TOKEN` are
from the published environment-variable reference, read the same day.

What is *not* verified is a live run: the Codex CLI is not installed in this
repository's container, so no fixture has been through this transport against
a real backend. The matrix says UNVERIFIED for this cell and means it. Treat
the first live run as the thing that moves it, not this docstring.

## Two shapes that differ from the sibling transports, on purpose

**The prompt is a positional argument, not stdin.** The usage string is the
only prompt-delivery shape the source proves; whether `codex exec` reads a
prompt from stdin is unverified, and guessing wrong means a process that
blocks until the timeout rather than one that fails. Fixture text is
repository-controlled public test data, which is the same standing
`eval_runtime_parity.py` already records for the requests it passes on a CLI
command line, so argv is an acceptable carrier for it. Never put a credential
in a fixture.

**The answer is read from a file, not from stdout.** `--output-last-message`
writes the final assistant message and nothing else, so there is no CLI
chrome to strip and no way for a tool trace to be scored as an answer. That
is the failure mode `_copilot_cli._may_carry_tool_trace` exists to refuse,
and this transport avoids it rather than detecting it.

## Billing

`CODEX_API_KEY` is Codex's own non-interactive API credential and
`OPENAI_API_KEY` can reach it through a `model_providers` `env_key`, so both
are stripped from the child environment. What is left is the `codex login`
session under `CODEX_HOME`, or `CODEX_ACCESS_TOKEN` for automation holding
one. `--ignore-user-config` drops `config.toml` without touching that login,
which is why the config directory can stay where the operator's session is.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from _cli_transport import (
    BASE_ENV_ALLOWLIST,
    build_envelope,
    minimal_process_env,
    run_cli,
    validate_timeout,
)

__all__ = ["_CodexCLIProvider"]

PROVIDER_LABEL = "Codex CLI"

#: Opt in to scoring a reply no transcript attributed to a model. Mirrors the
#: Copilot transport's variable, one per provider so accepting the loss on one
#: does not silently accept it on the other.
UNVERIFIED_MODEL_ENV = "EVAL_CODEX_ALLOW_UNVERIFIED_MODEL"

#: Credentials that would move the run onto metered OpenAI billing.
_BLOCKED_BILLING_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"})

_ENV_ALLOWLIST = BASE_ENV_ALLOWLIST | {"CODEX_ACCESS_TOKEN", "CODEX_HOME"}

_LAST_MESSAGE_FILE = "last-message.txt"


def _init_git_repository(sandbox: Path) -> None:
    """Make the sandbox a git repository.

    Codex treats a non-repository working directory as a refusal case rather
    than a warning. An empty repository costs one process and removes that
    whole failure class, and it keeps the sandbox empty in every way that
    matters to the eval: no tracked files, no history, no remotes.
    """
    try:
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=sandbox,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError(
            f"{PROVIDER_LABEL} sandbox setup failed: error=git_init_failed; "
            "process details redacted"
        ) from None


class _CodexCLIProvider:
    """Codex CLI driven as a one-shot `codex exec` subprocess."""

    name = "codex-cli"

    def __init__(self, *, executable: str = "codex", timeout: float = 900.0) -> None:
        self._executable = executable
        self._timeout = validate_timeout(timeout)
        self._provider_label = PROVIDER_LABEL
        self.system_fingerprint: str | None = None

    def _build_argv(self, model: str, last_message: Path, prompt: str) -> list[str]:
        """Build the fixed, shell-free `codex exec` invocation.

        `--sandbox read-only` is the narrowest of the three documented sandbox
        modes and the right one for a text eval: nothing this transport asks
        for needs a write. `--ephemeral` keeps the run out of the operator's
        rollout history, and `--ignore-user-config` keeps their `config.toml`
        out of the measurement.
        """
        return [
            self._executable,
            "exec",
            "--model",
            model,
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--output-last-message",
            str(last_message),
            prompt,
        ]

    def _build_env(self) -> dict[str, str]:
        # See the note in `_claude_cli._build_env`: sibling modules resolve to
        # Any, so the contract is pinned here.
        env: dict[str, str] = minimal_process_env(
            allow=_ENV_ALLOWLIST,
            blocked=_BLOCKED_BILLING_ENV,
            overrides={},
        )
        return env

    @classmethod
    def _unverified_model_allowed(cls) -> bool:
        """Report whether the operator opted in to an unconfirmed model.

        Anything other than an explicit affirmative reads as off, so a stray
        empty or "0" value fails closed.
        """
        raw = os.environ.get(UNVERIFIED_MODEL_ENV, "")
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _require_model_attribution_optin(cls) -> None:
        """Refuse to score a reply nothing attributed to a model.

        The Claude transport reads `modelUsage` and the Copilot transport
        reads a session transcript. Codex exposes no equivalent this
        repository has verified, so every reply from this cell is a score for
        a model the CLI accepted a `--model` flag for and never confirmed.
        Refusing by default keeps that loss visible instead of letting it ride
        in an archived run nobody can re-check.
        """
        if cls._unverified_model_allowed():
            return
        raise RuntimeError(
            f"{PROVIDER_LABEL} cannot confirm which model answered: no "
            "model-attributed output shape has been verified for `codex "
            "exec` from this repository, and the CLI accepts --model without "
            "echoing what it resolved. Scoring the reply anyway records a "
            f"result for an unknown model. Set {UNVERIFIED_MODEL_ENV}=1 to "
            "accept that loss knowingly, or use the codex-api cell, whose "
            "responses carry the served model id."
        )

    def _read_answer(self, last_message: Path) -> str:
        """Return the final assistant message the CLI wrote."""
        try:
            answer = last_message.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            raise RuntimeError(
                f"{PROVIDER_LABEL} API returned no choices; the CLI wrote no "
                "final-message file. Model identifier redacted."
            ) from None
        if not answer:
            raise RuntimeError(
                f"{PROVIDER_LABEL} API returned no choices; "
                "model identifier redacted"
            )
        return answer

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> str:
        # The CLI exposes no sampling controls. A fixture that needs sampling
        # determinism belongs on an HTTP provider.
        del max_tokens, temperature, seed

        self._require_model_attribution_optin()
        prompt = build_envelope(PROVIDER_LABEL, messages, system)
        self.system_fingerprint = None
        env = self._build_env()
        with tempfile.TemporaryDirectory(prefix="eval-codex-cli-") as outbox:
            last_message = Path(outbox) / _LAST_MESSAGE_FILE
            run_cli(
                self._build_argv(model, last_message, prompt),
                None,
                provider_label=PROVIDER_LABEL,
                env=env,
                timeout=self._timeout,
                prepare=_init_git_repository,
            )
            answer = self._read_answer(last_message)
        # Stays None: nothing in this transport confirmed the model, and the
        # operator opted in to that above rather than it being hidden here.
        return answer
