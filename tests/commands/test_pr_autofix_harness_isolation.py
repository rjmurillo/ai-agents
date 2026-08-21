"""The dispatch harness must not hand ambient secrets to the extracted block.

Refs #5094, PR #5176. `pr_autofix_dispatch_harness.run_dispatch` executes text
taken from a document on the branch under `bash -c`. What that text does is
whatever the branch says, so the environment it runs in is a security boundary
rather than a convenience: on a CI runner the process would otherwise hold the
job's token and any cloud credentials in scope, and on a developer machine the
whole shell environment. CodeRabbit reported the harness copying `os.environ`.

The fix is an allowlist in the harness. This file is the proof that the
allowlist is what the subprocess actually gets, which the allowlist's own
definition cannot establish: a later edit could reintroduce a merge with
`os.environ` and every other test in this directory would stay green, because
none of them reads a variable the harness was never supposed to pass.

Its own module because it is a property of the harness rather than of the tier
dispatch, and because `test_pr_autofix_tier_dispatch_runtime.py` is already near
the 500-line taste rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.commands.pr_autofix_dispatch_harness import (
    CI_ONLY_ENV,
    DISPATCH_DOCS,
    run_dispatch,
)

# Unique in the extracted block, so `block_edit`'s exactly-one assertion holds.
_ANCHOR = "TIER_KNOWN=yes"

# Shaped like the names that actually matter. The test asserts on the harness's
# behavior, not on this spelling, so it carries no secret and never has to.
_SENTINEL = "AI_AGENTS_FAKE_TOKEN_DO_NOT_SET"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_an_ambient_variable_does_not_reach_the_extracted_block(
    tmp_path: Path, doc: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A variable in the parent environment is invisible to the shell block.

    `${VAR-unset}` rather than `${VAR:-unset}` on purpose: the first substitutes
    only when the name is unset, the second also when it is set but empty. With
    the second spelling a harness that passed the variable through as an empty
    string would read as isolation, which is the wrong answer to the question.
    """
    monkeypatch.setenv(_SENTINEL, "secret-value")

    run = run_dispatch(
        tmp_path,
        doc,
        tier="T1",
        block_edit=(_ANCHOR, f"{_ANCHOR}\nprintf 'sentinel=%s\\n' \"${{{_SENTINEL}-unset}}\""),
    )

    assert "sentinel=unset" in run.stdout, (
        "the harness passed an ambient variable into the extracted block; "
        f"stdout was {run.stdout!r}"
    )
    assert "secret-value" not in run.stdout


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_isolation_probe_can_fail(
    tmp_path: Path, doc: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the probe reports a leak when there is one.

    Without this, the case above passes for a second reason nobody checks. If
    `block_edit` silently failed to place the `printf`, or the extracted block
    never ran, stdout would carry no `sentinel=` line at all and `in` would be
    false either way, which reads as isolation. Testing rule SHOULD 17: a
    control that cannot fail is not a passing control, so name the surviving
    input that makes its assertion false.

    `FAKE_TIER` is passed by the harness deliberately, so it stands in for a
    variable that does reach the block. Seeing its value proves the probe
    observes what the block can read, and therefore that "unset" above is a
    finding about the environment rather than about the probe.
    """
    monkeypatch.setenv(_SENTINEL, "secret-value")

    run = run_dispatch(
        tmp_path,
        doc,
        tier="T1",
        block_edit=(_ANCHOR, f"{_ANCHOR}\nprintf 'sentinel=%s\\n' \"${{FAKE_TIER-unset}}\""),
    )

    assert "sentinel=T1" in run.stdout, (
        "the probe could not observe a variable the harness does pass, so its "
        f"'unset' result proves nothing; stdout was {run.stdout!r}"
    )


def test_no_ci_only_name_is_allowlisted() -> None:
    """SHOULD-12's protection survives the denylist-to-allowlist change.

    The harness asserts this at import, which is where it belongs, but an
    import-time assertion is invisible in a run report: it either prevents the
    module from loading or says nothing. Restating it as a case means the
    failure names the rule rather than surfacing as a collection error.
    """
    from tests.commands.pr_autofix_dispatch_harness import _ENV_ALLOWLIST

    overlap = set(CI_ONLY_ENV) & set(_ENV_ALLOWLIST)

    assert not overlap, (
        f"{sorted(overlap)} is both runner-set and allowlisted, so a test can pass "
        "locally and fail in CI again"
    )
