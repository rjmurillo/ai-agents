"""Git-invocation safety contract tests for the reviewer-findings skill bundle.

Split out of ``test_reviewer_findings_routes.py`` to keep that file under the
repository's 500-line ceiling (``scripts/ci/taste_count_ratchet.py``); this
file grew fastest across PR #5178's review rounds, so it is the natural
extraction point. It later exceeded the same ceiling itself and was split
again: the disposition-to-outcome routing, responder gate-ordering, and reply
template tests moved to
``test_reviewer_findings_disposition_routing.py``, leaving this file scoped
to the CWE-78-safe git invocation mechanics. Shares the ``plugin_root``
fixture (``conftest.py``) and the parsing/lookup helpers (``_helpers.py``)
with both sibling test files; these apply to every test module in this
directory, not just the one that first imported them.

Covers every correctness and safety gap found across PR #5178's review
rounds in how a finding's untrusted text and cited path get into a git
command: CWE-78 safe invocation for both the needle text and the cited path
(including a path loaded from a file into a variable, never typed inline
into a command or a variable assignment), the per-line matching defect in
``git grep -f``/``-e`` (including under ``-z``), the empty-needle and
whitespace-only-needle ambiguities in a bare ``[ -s ]``/``wc -l`` check, the
shallow-checkout limit on ``git log -S``, and the current-state/provenance
distinction ``git log -S`` alone cannot make.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# pytest here runs under --import-mode=importlib (pyproject.toml), which never
# inserts a test file's own directory onto sys.path, so a plain
# `import _helpers` cannot resolve. Load the sibling module by file path
# instead, matching the wrapper idiom already used in
# tests/skills/pr-comment-responder/test_cluster_threads.py.
_HELPERS_PATH = Path(__file__).resolve().parent / "_helpers.py"
_helpers_spec = importlib.util.spec_from_file_location(
    "reviewer_findings_test_helpers", _HELPERS_PATH
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)

DISPOSITION_TOKENS = _helpers.DISPOSITION_TOKENS
ROUTER_SKILL = _helpers.ROUTER_SKILL
SKILL_NAME = _helpers.SKILL_NAME
TRIAGE_PHASE = _helpers.TRIAGE_PHASE
_bounded_section = _helpers._bounded_section
_missing_disposition_tokens = _helpers._missing_disposition_tokens
_phase_section = _helpers._phase_section
_read = _helpers._read
_read_reference = _helpers._read_reference
_row_disposition = _helpers._row_disposition
_workflow_phase_section = _helpers._workflow_phase_section


class TestPremiseVerificationIsDocumented:
    def test_reviewer_findings_names_the_provenance_commands(self, plugin_root: Path) -> None:
        """Positive: the two commands that expose a pre-fix-consistent finding."""
        text = _read(plugin_root, SKILL_NAME)
        assert "git grep -n -F" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer names git grep "
            f"-n -F (line-number-producing) for current-state verification"
        )
        assert "git log -S" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer names git log "
            f"-S for provenance verification"
        )

    def test_reviewer_findings_distinguishes_empty_needle_from_no_newline(
        self, plugin_root: Path
    ) -> None:
        """Positive: wc -l reports 0 for both an empty file and an unterminated
        single line, so the file must be checked non-empty too (Copilot on
        PR #5178). An empty needle means extraction failed, not that the
        claim is refuted; misclassifying it as False closes a thread on no
        evidence at all.
        """
        text = _read(plugin_root, SKILL_NAME)
        assert "non-empty" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer requires the "
            f"needle file to be checked non-empty before trusting a wc -l "
            f"of 0 as a single unterminated line"
        )
        assert "extraction failed" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer routes an "
            f"empty (failed-extraction) needle to Unverifiable rather than "
            f"a refuted False"
        )

    def test_reviewer_findings_rejects_a_whitespace_only_needle(
        self, plugin_root: Path
    ) -> None:
        """Positive: [ -s ] tests byte size, not content (Cursor Bugbot on
        PR #5178, commit 88b3ea11f).

        A needle holding only spaces or a blank line has nonzero byte size,
        so `[ -s <needle-file> ]` alone reports it non-empty and a
        single-line count of 1 makes it look like a real one-line claim.
        Verified: `[ -s ]` on a one-space file reports non-empty, and
        `git grep -F -f` on that file then matches any haystack line
        containing a space, a false confirmation on almost any real code.
        The skill must use a non-whitespace check (`grep -q
        '[^[:space:]]'`), not `[ -s ]` alone, to catch this.
        """
        text = _read(plugin_root, SKILL_NAME)
        assert "[^[:space:]]" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer requires a "
            f"non-whitespace character in the needle file; a needle holding "
            f"only spaces would pass a bare `[ -s ]` check and let `git "
            f"grep -F -f` false-confirm on any haystack line containing a "
            f"space"
        )
        assert "whitespace-only" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer names the "
            f"whitespace-only needle as a failed-extraction case routed to "
            f"Unverifiable"
        )

    def test_a_bare_s_flag_check_is_what_the_whitespace_guard_would_catch(
        self,
    ) -> None:
        """Negative control: the same substring checks must reject wording
        that relies on `[ -s ]` alone, proving they discriminate.
        """
        unfixed = (
            "Check the file is non-empty before trusting a `wc -l` of 0, "
            "which an empty file also reports"
        )
        assert "[^[:space:]]" not in unfixed, (
            "the unfixed wording unexpectedly contains the non-whitespace "
            "pattern, so the positive check above would not discriminate "
            "against it"
        )

    def test_reviewer_findings_counts_logical_lines_not_newline_bytes(
        self, plugin_root: Path
    ) -> None:
        """Positive: wc -l undercounts a needle whose last line has no
        trailing newline (Copilot on PR #5178).

        `wc -l` counts newline *bytes*, not logical lines: a two-line needle
        whose final line lacks a trailing newline has only one embedded
        newline, so `wc -l` reports 1 (verified with `printf
        'line1\\nline2'`, which is 2 logical lines but reports 1). Reading
        that 1 as "exactly one line" passes the single-line gate on a needle
        that is actually two lines, and `git grep -n -F -f` then matches per
        line and can false-confirm on either one alone, the same failure
        mode the gate exists to prevent. `grep -c ''` counts logical records
        regardless of a missing trailing newline (verified on the same
        input: 2) and is what the skill must use for the line-count check.
        """
        text = _read(plugin_root, SKILL_NAME)
        assert "grep -c ''" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer uses `grep "
            f"-c ''` to count the needle file's logical lines; if it fell "
            f"back to `wc -l` alone, a two-line needle whose final line "
            f"lacks a trailing newline would report 1 and pass the "
            f"single-line gate it does not belong in"
        )
        assert "newline bytes" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer explains "
            f"that `wc -l` counts newline bytes rather than logical lines, "
            f"so a reader has no reason to prefer `grep -c ''` over the "
            f"more familiar `wc -l`"
        )

    def test_wc_l_alone_is_what_the_logical_line_count_check_would_catch(self) -> None:
        """Negative control: the same substring checks must reject the
        unfixed wording, proving they discriminate rather than passing
        unconditionally.
        """
        unfixed = (
            "confirm it is non-empty and exactly one line (`[ -s "
            "<needle-file> ]` and `wc -l <needle-file>` reports 1, or 0 "
            "when the last line has no trailing newline)"
        )
        assert "grep -c ''" not in unfixed, (
            "the unfixed wording unexpectedly contains `grep -c ''`, so "
            "the positive check above would not discriminate against it"
        )
        assert "newline bytes" not in unfixed, (
            "the unfixed wording unexpectedly explains newline-byte "
            "counting, so the positive check above would not discriminate "
            "against it"
        )

    def test_reviewer_findings_quotes_the_path_argument_too(self, plugin_root: Path) -> None:
        """Positive: <path> is also drawn from the untrusted finding, and a
        bare `-- <path>` does not make it safe (Copilot on PR #5178, then
        again on commit 88b3ea11f: `--` ends Git option parsing, it does not
        stop a crafted path from being typed as shell source).

        `-- <path>` in prose reads as protection but is not: if an agent
        follows it literally, the finding-controlled path text gets typed
        straight into the command, and a path containing `$(...)` or a
        quote breaks out there regardless of the `--` boundary. The safe
        contract loads the path from a file into a variable first
        (`PATH_SPEC=$(cat <path-file>)`) and references only the quoted
        `"$PATH_SPEC"` after `--`, never the raw `<path>` placeholder typed
        inline. A fix that only hardens the needle and leaves `<path>`
        spliced into the command string, quoted-looking `--` boundary or
        not, reopens the same CWE-78 shape one argument over.
        """
        text = _read(plugin_root, SKILL_NAME)
        assert '-- "$PATH_SPEC"' in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer shows the "
            f"path passed as the quoted, file-loaded `\"$PATH_SPEC\"` "
            f"variable after a literal '--'"
        )
        assert "PATH_SPEC=$(cat" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer shows "
            f"PATH_SPEC loaded by reading a file (`$(cat <path-file>)`); "
            f"without this, a reader has no safe way to get the "
            f"finding-controlled path into the variable in the first place"
        )
        assert "-- <path>" not in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} still shows the raw "
            f"`-- <path>` placeholder typed inline in a command; `--` ends "
            f"Git option parsing but does not stop a crafted path from "
            f"being typed as shell source when an agent follows the "
            f"example literally"
        )
        assert "never splice it into" in text or "never splice it in" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} dropped the instruction "
            f"not to splice the finding-controlled path into a larger shell "
            f"string"
        )

    def test_a_bare_dash_dash_path_is_what_the_quoting_check_would_catch(
        self,
    ) -> None:
        """Negative control: the same substring checks must reject the
        unfixed `-- <path>` wording, proving `--` alone does not satisfy
        them.
        """
        unfixed = (
            "pass it after a literal `--` where the command supports it, "
            "for example `git grep -n -F -f <needle-file> <commit> -- "
            "<path>`, which ends option parsing so a value starting with "
            "`-` cannot be read as a flag"
        )
        assert '-- "$PATH_SPEC"' not in unfixed, (
            "the unfixed wording unexpectedly contains the quoted "
            "PATH_SPEC form, so the positive check above would not "
            "discriminate against it"
        )
        assert "PATH_SPEC=$(cat" not in unfixed, (
            "the unfixed wording unexpectedly shows PATH_SPEC loaded from "
            "a file, so the positive check above would not discriminate "
            "against it"
        )
        assert "-- <path>" in unfixed, (
            "the bare-path detection did not flag a line reproducing the "
            "unsafe `-- <path>` form verbatim, so it would not catch a "
            "real regression to that form either"
        )

    def test_reviewer_findings_git_show_never_uses_a_bare_path(self, plugin_root: Path) -> None:
        """Positive: `--` does not protect git show's combined revision spec (Copilot on PR #5178).

        `--` ends option parsing for a command that takes a separate pathspec
        argument (git grep, git log -S), but git show's `<commit>:<path>`
        form is one argument with no `--` boundary at all, so `-- <path>`
        after it would be meaningless and `git show <commit>:<path>` typed
        literally still splices the untrusted path into the command. The fix
        loads the path into a variable and quotes the whole revision spec
        (`git show "<reviewed-commit>:$PATH_SPEC"`); assert every `git show`
        invocation uses that quoted form, and that none types a bare
        `<path>` directly after a colon.
        """
        text = _read(plugin_root, SKILL_NAME)
        git_show_lines = [line for line in text.splitlines() if "git show" in line]
        assert git_show_lines, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer mentions git show "
            f"at all; this test has nothing to check"
        )
        bare_path_after_colon = [line for line in git_show_lines if ":<path>" in line]
        assert not bare_path_after_colon, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} has a git show invocation "
            f"with an unquoted <path> spliced directly into the revision spec: "
            f"{bare_path_after_colon}"
        )
        quoted_form = [line for line in git_show_lines if '"<reviewed-commit>:$PATH_SPEC"' in line]
        assert quoted_form, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer shows git show "
            f'using the quoted `"<reviewed-commit>:$PATH_SPEC"` revision spec '
            f"(the path loaded into a variable first, never typed inline)"
        )

    def test_a_bare_colon_path_is_what_the_git_show_check_would_catch(self) -> None:
        """Negative control: the same substring check must flag the unsafe form."""
        unsafe = "run `git show <reviewed-commit>:<path>` and search the output"
        bare_path_after_colon = [line for line in unsafe.splitlines() if ":<path>" in line]
        assert bare_path_after_colon, (
            "the bare-path detection did not flag a line that literally "
            "splices <path> after the colon, so it would not catch a real "
            "regression to the unsafe git show <commit>:<path> form either"
        )

    def test_reviewer_findings_disables_git_pathspec_magic(self, plugin_root: Path) -> None:
        """Positive: quoting stops shell injection, not git's own pathspec
        magic (Copilot on PR #5178, commit 2eeeda1cc).

        `-- "$PATH_SPEC"` is safe from shell metacharacters, but git itself
        still interprets a value starting with `:` as pathspec magic
        (`:(glob)**`, `:(exclude)...`) once past `--`, regardless of shell
        quoting. Verified: `git grep -n -F -e "secret" -- ':(glob)**'`
        matched every file in a throwaway repo instead of failing on the
        literal, nonexistent path `:(glob)**`; adding
        `--literal-pathspecs` before the subcommand made the same call
        correctly find nothing. Every `git grep` and `git log` invocation
        in the skill must carry that flag; `git show`'s `<rev>:<path>`
        blob-lookup form is exempt (verified separately: `git show
        "HEAD::(glob)**"` finds nothing rather than expanding, because it
        is not a pathspec argument).
        """
        text = _read(plugin_root, SKILL_NAME)
        assert "--literal-pathspecs" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer requires "
            f"--literal-pathspecs; a cited path starting with `:` (e.g. "
            f"`:(glob)**`) would be interpreted as git pathspec magic and "
            f"search unrelated files, even with $PATH_SPEC correctly "
            f"shell-quoted"
        )
        # Match on "grep -n -F -f" without a "git " prefix: the real
        # invocation reads "git --literal-pathspecs grep -n -F -f", so a
        # "git grep -n -F -f" search would never match it even when the
        # flag is correctly present, and would falsely report the
        # invocation missing entirely (the disposition table's bare
        # "git grep -n -F" mention has no trailing "-f", so it does not
        # collide with this filter).
        grep_lines = [line for line in text.splitlines() if "grep -n -F -f" in line]
        assert grep_lines, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer names the "
            f"git grep -n -F -f invocation; this test has nothing to check"
        )
        unguarded_grep = [line for line in grep_lines if "--literal-pathspecs" not in line]
        assert not unguarded_grep, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} has a git grep "
            f"invocation missing --literal-pathspecs: {unguarded_grep}"
        )
        # 'log -S "$NEEDLE"' alone also matches a prose sentence describing
        # git log -S's general semantics ("only proves the string's
        # occurrence count changed..."), not a command example; require
        # <reviewed-commit> on the same line too, since real invocations
        # keep the pinned commit on the same line even where -- "$PATH_SPEC"
        # wraps to the next one.
        log_s_lines = [
            line
            for line in text.splitlines()
            if 'log -S "$NEEDLE"' in line and "<reviewed-commit>" in line
        ]
        assert log_s_lines, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer names a "
            f"git log -S \"$NEEDLE\" <reviewed-commit> invocation; this "
            f"test has nothing to check"
        )
        unguarded_log = [line for line in log_s_lines if "--literal-pathspecs" not in line]
        assert not unguarded_log, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} has a git log -S "
            f"invocation missing --literal-pathspecs: {unguarded_log}"
        )

    def test_a_bare_git_grep_line_is_what_the_pathspec_guard_would_catch(self) -> None:
        """Negative control: the same per-line checks must flag a git grep
        or git log -S invocation missing --literal-pathspecs.
        """
        unfixed = (
            'run `git grep -n -F -f <needle-file> <reviewed-commit> -- "$PATH_SPEC"`\n'
            'then `git log -S "$NEEDLE" <reviewed-commit> -- "$PATH_SPEC"`'
        )
        grep_lines = [line for line in unfixed.splitlines() if "git grep -n -F -f" in line]
        unguarded_grep = [line for line in grep_lines if "--literal-pathspecs" not in line]
        assert unguarded_grep, (
            "the pathspec guard did not flag a git grep line missing "
            "--literal-pathspecs, so it would not catch a real regression "
            "to the unguarded form either"
        )
        log_s_lines = [
            line
            for line in unfixed.splitlines()
            if 'log -S "$NEEDLE"' in line and "<reviewed-commit>" in line
        ]
        unguarded_log = [line for line in log_s_lines if "--literal-pathspecs" not in line]
        assert unguarded_log, (
            "the pathspec guard did not flag a git log -S line missing "
            "--literal-pathspecs, so it would not catch a real regression "
            "to the unguarded form either"
        )

    def test_reviewer_findings_names_the_shallow_checkout_caveat(self, plugin_root: Path) -> None:
        """Positive: a shallow CI checkout limits what git log -S can prove (Copilot on PR #5178).

        This repository's CI checks out with fetch-depth: 1
        (.github/workflows/claude.yml:47,88), so a session running here may
        be shallow too. Empirically, a shallow clone still answers a
        single-commit presence question correctly (git diffs the shallow
        boundary as a root commit), but it cannot answer a claim about when
        a value was introduced or removed across commits it never fetched.
        """
        text = _read(plugin_root, SKILL_NAME)
        assert "is-shallow-repository" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer tells the "
            f"reader to check for a shallow checkout before trusting a "
            f"multi-commit provenance claim"
        )
        assert "fetch --unshallow" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer names the "
            f"recovery (git fetch --unshallow) for a provenance claim a "
            f"shallow checkout cannot settle"
        )

    def test_reviewer_findings_warns_git_log_s_does_not_prove_current_state(
        self, plugin_root: Path
    ) -> None:
        """Positive: git log -S matches an add-then-remove pair equally (Cursor Bugbot on PR #5178).

        Verified empirically: a two-commit history that adds a multi-line
        string and then removes it still returns both commits from
        `git log -S` bounded at the removal commit, even though the removal
        commit's tree does not contain the string. A finding quoting
        already-removed pre-fix text can therefore be marked true on
        `git log -S` output alone. Also verified that the obvious recovery,
        piping `git show` output through `grep -F "$NEEDLE"`, does not work
        either: fixed-string grep still splits a multi-line pattern per line
        (a needle sharing only its first two of three lines with an
        unrelated haystack still matched). The fix uses a literal whole-block
        comparison instead (a tool that does not split on newlines), not
        another grep-based recipe.
        """
        text = _read(plugin_root, SKILL_NAME)
        assert "not that it is present now" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer warns that a "
            f"git log -S match alone does not prove current presence"
        )
        assert "does not split on newlines" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer names a "
            f"whole-block comparison tool for a current-state multi-line "
            f"claim neither git grep nor git log -S can settle alone"
        )
        assert "python3 -c" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer prescribes the "
            f"Python substring check as the whole-block comparison; grep -F "
            f"was empirically shown to split a multi-line pattern per line "
            f"too (even with a single -e argument), so it cannot be the "
            f"prescribed recovery"
        )

