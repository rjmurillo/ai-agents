"""Shared stubs for the pre_pr main entry point tests.

Used by test_pre_pr_main.py, test_pre_pr_banner_shown.py, and
test_pre_pr_banner_suppressed.py. Those files were split from
tests/test_validation_pre_pr.py (issue #6211) so that xdist ``loadfile``
workers stay balanced; the stubs live here so the three files share one copy.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from scripts.validation.pre_pr import run_all_validations


def sequence_with_passing_corpus_gates() -> tuple[Any, ...]:
    # pre_pr loads pre_pr_sequence as a flat module for direct script execution.
    # Read through the function so the patch targets that exact module identity.
    sequence = run_all_validations.__globals__["_SEQUENCE"]
    corpus_gates = {
        "Documented Interpreter Portability",
        "Duplicate Test Helper Detection",
        "Subprocess Encoding Convention",
        "Unreachable Code Detection",
        # Reads the real .git directory via `git rev-parse --git-path hooks`.
        # healthy_git_run's rev-parse branch answers every rev-parse call with
        # "0" * 40 (a plausible commit SHA for HEAD-style queries), which this
        # gate's --git-path call turns into a nonsense path and then correctly
        # reports as unhealthy. The gate's own correctness against a real git
        # tree is covered by tests/validation/test_check_git_hook_health.py;
        # here it is real-git-state-dependent noise the same way the other
        # corpus gates are real-filesystem-dependent noise.
        "Git Hook Health (core.hooksPath)",
        # check_adr_links.py's validate_adr_links() calls `git ls-files -z
        # *.md` via git_ls_markdown(). healthy_git_run's blanket
        # `else: stdout = ""` branch answers that call (it matches neither
        # "symbolic-ref" nor "rev-parse"), so git_ls_markdown() returns an
        # empty list under this mock regardless of the real repo's tracked
        # files. check_adr_links.py's round-9 fix (PR #5209) treats a
        # zero-file result as a wrong-but-valid repository root and fails
        # closed, which is correct against a real git invocation but is a
        # mock artifact here, not a real empty corpus: real-filesystem-
        # dependent noise the same way the other corpus gates above are.
        "ADR Link Resolution",
        # `check_index_line_endings.py` captures `git ls-files --eol -z` in
        # bytes, because a pathname is bytes and `errors="replace"` destroys
        # undecodable ones irreversibly (issue #5475). `healthy_git_run`
        # answers every call with a `str` stdout, so the gate's `.decode` gets
        # an object that has no such method and the gate reports a mock
        # artifact rather than a line-ending verdict. The gate's own behavior
        # is covered across tests/validation/test_check_index_line_endings*.py,
        # whose roster lives in
        # tests/validation/index_line_endings_helpers.py rather than being
        # restated here, and the gate's registration is covered in
        # tests/validation/test_pre_pr_index_line_endings_wiring.py.
        "Index Line Endings",
        # Same mock artifact as "ADR Link Resolution" above, from the same
        # blanket `else: stdout = ""` branch. check_skill_adr_bindings.py
        # enumerates candidates with `git ls-files -z -- *SKILL.md` through
        # count_ratchet.tracked_files, so under this mock it sees zero
        # candidates and fails closed with EXIT_CONFIG. That fail-closed is the
        # point of the gate: a run that examined nothing must not report what a
        # completed run reports (ci-scripts.md MUST 11 and 12), and a
        # zero-candidate tree previously printed `improved: 0 of a permitted 16`
        # and invited lowering the ceiling to nothing. Against a real git
        # invocation the repository offers 222 manifests, so this is
        # real-filesystem-dependent noise here rather than an empty corpus. The
        # gate's own behavior is covered in
        # tests/validation/test_check_skill_adr_bindings.py and its registration
        # in tests/validation/test_skill_adr_bindings_wiring.py.
        "Skill ADR Bindings (ratchet)",
        # Pipes a malformed envelope through the validator CLI with
        # `subprocess.run` and requires a non-zero exit. The tests that use
        # these stubs patch `subprocess.run` with `healthy_git_run`, which answers every call
        # with exit 0, so the CLI appears to accept the malformed envelope and
        # the gate correctly reports it. Mock artifact, not a real acceptance.
        # The gate's behavior is covered in
        # tests/validation/test_check_skill_output_envelopes.py.
        "Skill Output Envelope",
        # Spawns `build/scripts/build_all.py --check` against the real
        # repository root. That child is not mocked: the gate reaches it
        # through `subprocess.Popen`
        # (scripts/validation/check_generated_staleness.py:224) and
        # the tests that use these stubs patch `subprocess.run` only. So this gate is not merely
        # real-corpus-dependent like the ones above, it MUTATES the real
        # corpus: build_all regenerates every generator-owned file and then
        # restores its snapshot, and a sibling xdist worker reading one of
        # those files mid-write sees it truncated. Issue #5502 recorded that
        # as `src/vs-code-agents/skillbook.agent.md` read empty; the same
        # window turned `tests/test_pr_identity_gate.py` red on
        # `src/copilot-cli/agents/analyst.agent.md`. The gate's own behavior
        # is covered by tests/validation/test_check_generated_staleness.py,
        # and its registration by
        # tests/validation/test_pre_pr_sequence_registry.py.
        "Generated Artifact Staleness",
    }
    return tuple(
        replace(gate, run=lambda _repo_root, _args: True) if gate.name in corpus_gates else gate
        for gate in sequence
    )


def sequence_with_failing_python_syntax() -> tuple[Any, ...]:
    sequence = run_all_validations.__globals__["_SEQUENCE"]
    return tuple(
        replace(gate, run=lambda _repo_root, _args: False)
        if gate.name == "Python Syntax (compile gate)"
        else gate
        for gate in sequence
    )


def healthy_git_run(*args: Any, **_kwargs: Any) -> Any:
    """Model a working toolchain: every tool exits 0, git answers plausibly.

    A blanket ``stdout = ""`` makes ``git symbolic-ref --short
    refs/remotes/origin/HEAD`` look like a repository with no remote HEAD, and
    the count-ratchet gate fails closed on exactly that. Answering per command
    keeps these tests on the all-pass path without feeding a branch name to
    every other gate that reads stdout.
    """
    argv = args[0] if args else []
    if "symbolic-ref" in argv:
        stdout = "origin/main"
    elif "rev-parse" in argv or "merge-base" in argv:
        stdout = "0" * 40
    else:
        stdout = ""
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
