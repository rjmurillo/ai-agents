Verified the argv-less behavior locally and audited every caller. The factual claim is correct -- `markdownlint-cli2` with no argv now reports `Linting: 0 file(s)`. The operational claim ("CI workflow configuration must be updated") does not hold: there is no CI workflow that invokes `markdownlint-cli2` without argv to update.

**Evidence (run on this branch, b87bce81):**

```
$ grep -rln "markdownlint" .github/workflows/
(no matches)

$ grep -rn "markdownlint-cli2" scripts/ .github/workflows/ | grep -v "install\|--help\|--version\|setup\|comment"
scripts/validation/pre_pr.py:199:    exit_code, _, _ = _run_subprocess(["npx", "markdownlint-cli2", "--fix", "**/*.md"])
```

The only lint caller in the repository is `scripts/validation/pre_pr.py:199`, which already passes `**/*.md` explicitly. It is unaffected by the config-globs removal. The remaining `markdownlint-cli2` references in `scripts/bootstrap-vm.sh` and `.github/actions/setup-code-env/action.yml` are installer/availability checks (`--help`), not lint runs.

**On the "569 errors" / "CI is now green" framing:** the 569 errors come from the explicit full-repo invocation (`pre_pr.py`'s argv `**/*.md`), and the PR description reports them as **pre-existing** content findings unrelated to this PR. They were never enforced as a CI blocker -- there is no markdown-lint CI gate. The PR's CI green-state reflects independent gates (Python tests, agent drift, security review, etc.) passing on a one-file config change. This PR does not bypass any quality gate; it makes the on-edit hook usable and unblocks the explicit `pre_pr.py` walk by 68x.

If a markdown-lint CI gate is desirable as a separate concern, that should be a new workflow with `markdownlint-cli2 "**/*.md" --no-fix` or similar -- it would not be a regression of this PR. Happy to file a follow-up issue if the project wants that gate.

Resolving on the basis that no caller in this repo is broken by the change. If you can point at a specific argv-less invocation I missed, please flag it.
