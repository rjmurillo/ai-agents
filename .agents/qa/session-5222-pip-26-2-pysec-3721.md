---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5222-9e1ebd2b8-pip-26-2-pysec-3721.json
qaCommit: 12aafc3a91916fc54b0278b37c6526e32efca59e
---

# QA: pip 26.1.2 to 26.2 for PYSEC-2026-3721 (issue #5222)

**Branch**: `claude/pip-26-2-pysec-3721`
**Validated at commit**: `12aafc3a91916fc54b0278b37c6526e32efca59e`
**Session log**: `.agents/sessions/2026-08-21-session-5222-9e1ebd2b8-pip-26-2-pysec-3721.json`

## Verdict

PASS. The change is one pin plus the comments that name it. Both halves of the
claim were established by execution rather than by reading the job name.

## The failure is real and is on the base branch

Main run [32486211457](https://github.com/rjmurillo/ai-agents/actions/runs/32486211457)
at commit `63bca8796` lists `Python Security Checks` among its failed jobs. That
predates any branch involved here.

The newest main run of the same workflow reports `success` and looks like a
refutation. It is not: in [32486296161](https://github.com/rjmurillo/ai-agents/actions/runs/32486296161)
the job's conclusion is `skipped`, because the commit was documentation only and
the path filter short-circuited it. A green run in which the job never executed
is not evidence the job passes. Recording this because reading that run as a pass
would have closed the investigation with the wrong answer.

## The vulnerability, reproduced

Clean virtualenv, no code from this repository:

```
$ python3 -m venv /tmp/pipaudit
$ /tmp/pipaudit/bin/pip install "pip==26.1.2" pip-audit
$ /tmp/pipaudit/bin/pip-audit
Name Version ID              Fix Versions
pip  26.1.2  PYSEC-2026-3721 26.2
```

## The fix, reproduced

```
$ python3 -m venv /tmp/pipnew
$ /tmp/pipnew/bin/pip install "pip==26.2" pip-audit
$ /tmp/pipnew/bin/pip --version
pip 26.2 from /tmp/pipnew/lib/python3.14/site-packages/pip (python 3.14)
$ /tmp/pipnew/bin/pip-audit
No known vulnerabilities found
exit=0
```

## The trap in that result, and why the ignores stay

`No known vulnerabilities found` reads as license to drop the three
`--ignore-vuln` flags, which the comment block explicitly invites on a version
bump. It is not license, and dropping them would have turned this check red again.

That virtualenv resolved a different dependency set than CI runs:

```
$ /tmp/pipnew/bin/pip list | grep -i pygments
Pygments                2.21.0
$ uv run --frozen python -c "import pygments; print(pygments.__version__)"
2.19.2
```

`CVE-2026-4539` is about pygments 2.19.2, which the project pins and the probe
venv did not have. So the clean audit answers for a tree CI does not use. All
three ignores are retained and the comment now says the re-check is conditioned
on 26.2. Retiring them belongs to issue #1778, measured against the real tree.

This is the general shape worth carrying: a probe run in a different environment
than the one under test can return the right answer to the wrong question.

## The duplication this change had to sweep

The pin appeared in four places in one block: the install line and three comment
lines restating `26.1.2` as rationale. A bump touching only the install line
would have left prose describing a version the workflow no longer installs.

That is the same defect class that broke
`tests/ci/test_validate_vendor_provenance.py` when Renovate bumped
`astral-sh/setup-uv`: a value restated next to the thing that owns it. All four
moved together. The comment now records that this pin has moved twice, for the
same reason both times, and tells the next reader to move every mention with it.

One occurrence was deliberately left alone.
`tests/validation/test_check_ci_dependency_pins.py:254` uses the string
`pip==26.1.2` as fixture data for "an undeclared package is not checked" and
asserts `== []` for any version. It is not a pin and nothing about it depends on
which pip CI installs. Changing it would be churn that implies a coupling that
does not exist.

## Verification run

```
check_ci_dependency_pins.py    exit 0
pytest.yml                     parses as YAML
test_check_ci_dependency_pins  52 passed
pre_pr.py                      all validations passed
grep '26\.1\.2' pytest.yml     only the two historical references in the
                               provenance comment, which are correct as history
```

## What this QA does not claim

It does not claim `Python Security Checks` is green. That runs on the PR against
the real dependency tree, and only that run settles it. The evidence above says
the vulnerable version is gone and the ignores that were still needed are still
present. The check itself is the gate, and it has not run yet at the time of
writing.
