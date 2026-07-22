# CodeQL Integration Rollout Checklist

This checklist validates the current CodeQL integration. The implementation uses Python scripts in `.codeql/scripts/`, shared config files in `.github/codeql/`, and a two-tier strategy from ADR-041 as amended on 2026-07-21.

The automatic edit-time hook was retired on 2026-07-21. Do not include it in rollout, rollback, validation, or troubleshooting steps. Use explicit quick scans through `invoke_codeql_scan.py --quick-scan`.

---

## Pre-Rollout

Verify all prerequisites before rollout:

- [ ] **Implementation complete**
  - [ ] CLI installer exists: `.codeql/scripts/install_codeql.py`
  - [ ] Integration installer exists: `.codeql/scripts/install_codeql_integration.py`
  - [ ] Scan script exists: `.codeql/scripts/invoke_codeql_scan.py`
  - [ ] Config validator exists: `.codeql/scripts/test_codeql_config.py`
  - [ ] Diagnostics script exists: `.codeql/scripts/get_codeql_diagnostics.py`
  - [ ] Rollout validator exists: `.codeql/scripts/test_codeql_rollout.py`
  - [ ] Shared config exists: `.github/codeql/codeql-config.yml`
  - [ ] Quick config exists: `.github/codeql/codeql-config-quick.yml`
  - [ ] CI workflow exists: `.github/workflows/codeql-analysis.yml`
  - [ ] Integration test workflow exists: `.github/workflows/test-codeql-integration.yml`
  - [ ] Claude Code skill exists: `.claude/skills/codeql-scan/`

- [ ] **Tests passing**
  - [ ] CodeQL script unit tests pass.
  - [ ] CodeQL skill tests pass.
  - [ ] Rollout validator tests pass.
  - [ ] Run targeted pytest command:

    ```bash
    uv run pytest tests/test_install_codeql.py tests/test_install_codeql_integration.py tests/test_invoke_codeql_scan_py.py tests/test_test_codeql_config.py tests/test_get_codeql_diagnostics.py tests/test_test_codeql_rollout.py tests/skills/codeql-scan/test_invoke_codeql_scan_skill.py
    ```

- [ ] **Documentation reviewed**
  - [ ] User guide: `docs/codeql-integration.md`
  - [ ] Architecture guide: `docs/codeql-architecture.md`
  - [ ] Rollout checklist: `docs/codeql-rollout-checklist.md`
  - [ ] ADR-041 amendment reflected: `.agents/architecture/ADR-041-codeql-integration.md`
  - [ ] ADR-042 Python migration reference reflected: `.agents/architecture/ADR-042-python-migration-strategy.md`

- [ ] **ADR status understood**
  - [ ] ADR-041 remains the CodeQL strategy record.
  - [ ] ADR-041 was amended on 2026-07-21 to two live tiers.
  - [ ] ADR-042 supersedes the older scripting-language decision for new internal automation.
  - [ ] Issue #3219 tracks the deferred portable automatic scanning rebuild.

---

## Rollout Steps

### Step 1: Run Automated Deployment Validation

```bash
python3 .codeql/scripts/test_codeql_rollout.py --ci
```

Optional JSON output:

```bash
python3 .codeql/scripts/test_codeql_rollout.py --format json --ci
```

Expected result:

- [ ] Validator exits 0.
- [ ] CLI installation checks pass.
- [ ] Config file checks pass.
- [ ] Script existence checks pass.
- [ ] CI workflow checks pass.
- [ ] Local development checks pass.
- [ ] Documentation checks pass.
- [ ] Gitignore checks pass for `.codeql/cli/`, `.codeql/db/`, `.codeql/results/`, and `.codeql/logs/`.

### Step 2: Verify CLI Installation

```bash
python3 .codeql/scripts/install_codeql.py --ci --force
.codeql/cli/codeql version
```

Expected result:

- [ ] CLI downloads successfully.
- [ ] CLI executable exists at `.codeql/cli/codeql` on Linux.
- [ ] `codeql version` prints a version.

### Step 3: Validate Full Configuration

```bash
python3 .codeql/scripts/test_codeql_config.py --config-path .github/codeql/codeql-config.yml --ci
```

Expected result:

- [ ] Config file exists.
- [ ] YAML is valid.
- [ ] Query packs are resolvable.
- [ ] Medium-or-higher filtering remains configured.

### Step 4: Validate Quick Configuration

```bash
python3 .codeql/scripts/test_codeql_config.py --config-path .github/codeql/codeql-config-quick.yml --ci
```

Expected result:

- [ ] Quick config file exists.
- [ ] YAML is valid.
- [ ] Targeted query IDs are valid.
- [ ] Low severity and recommendation filters remain configured.

### Step 5: Test Full Local Scan

```bash
python3 .codeql/scripts/invoke_codeql_scan.py --languages python actions --format console
```

Expected result:

- [ ] Databases are created under `.codeql/db`.
- [ ] Results are written under `.codeql/results`.
- [ ] Console output summarizes the scan.
- [ ] Exit code is 0 when no scan failure occurs.

If the scan fails:

```bash
python3 .codeql/scripts/get_codeql_diagnostics.py --output-format markdown
python3 .codeql/scripts/test_codeql_config.py --ci
```

### Step 6: Test Quick On-Demand Scan

```bash
python3 .codeql/scripts/invoke_codeql_scan.py --quick-scan --use-cache --format console
```

Expected result:

- [ ] Script uses quick scan mode.
- [ ] Default config switches to `.github/codeql/codeql-config-quick.yml`.
- [ ] Cached databases are reused when valid.
- [ ] Results are written under `.codeql/results`.
- [ ] Scan finishes within the local 60 second default budget.

### Step 7: Test Claude Code Skill

In a Claude Code session:

```bash
/codeql-scan
```

Direct wrapper checks:

```bash
python3 .claude/skills/codeql-scan/scripts/invoke_codeql_scan.py --operation validate
python3 .claude/skills/codeql-scan/scripts/invoke_codeql_scan.py --operation full
python3 .claude/skills/codeql-scan/scripts/invoke_codeql_scan.py --operation quick
```

Expected result:

- [ ] Skill loads without errors.
- [ ] Validate operation succeeds.
- [ ] Full operation invokes the core scan path.
- [ ] Quick operation invokes the targeted local scan path.
- [ ] Results are clear enough for a developer to act.

### Step 8: Test CI/CD Workflow

Use a normal PR that changes a scannable file. Do not create throwaway branches if a real rollout PR already exists.

Expected workflow behavior:

- [ ] `.github/workflows/codeql-analysis.yml` runs on the PR.
- [ ] `check-paths` detects scannable file changes.
- [ ] GitHub CodeQL action initializes with `.github/codeql/codeql-config.yml`.
- [ ] CodeQL analysis runs for the workflow matrix.
- [ ] SARIF is uploaded to `.codeql/results/<language>.sarif` in the workflow workspace.
- [ ] SARIF artifact uploads with the `codeql-results-<language>` name.
- [ ] GitHub Security tab receives uploaded results.
- [ ] Required check reports pass or fails with actionable findings.

For non-scannable changes:

- [ ] `check-paths` reports no scannable files.
- [ ] Skip job creates a passing check.
- [ ] Required status checks are still satisfied.

### Step 9: Test Integration Workflow

The second workflow proves the local Python scripts work in CI.

Expected workflow facts for `.github/workflows/test-codeql-integration.yml`:

- [ ] Runs on `ubuntu-24.04` for CodeQL CLI jobs.
- [ ] Installs the CLI with:

  ```bash
  python3 .codeql/scripts/install_codeql.py --ci --force
  ```

- [ ] Validates config with:

  ```bash
  python3 .codeql/scripts/test_codeql_config.py --ci
  ```

- [ ] Scans the language matrix `[actions, python]` with:

  ```bash
  python3 .codeql/scripts/invoke_codeql_scan.py --languages "$SCAN_LANGUAGE" --ci --format console
  ```

- [ ] Verifies SARIF files under `.codeql/results`.

### Step 10: Review SARIF Output

Inspect generated SARIF locally or from workflow artifacts:

```bash
python3 - <<'PY'
import json
from pathlib import Path
for path in Path('.codeql/results').glob('*.sarif'):
    data = json.loads(path.read_text())
    print(path, data.get('version'), len(data.get('runs', [])))
PY
```

Verify:

- [ ] SARIF version is present.
- [ ] Each file has at least one run.
- [ ] Results include rule ID, message, and location when findings exist.
- [ ] No secrets are present in output.
- [ ] Files are not staged for commit.

---

## Post-Rollout

### Monitor First Production PR

- [ ] CodeQL Analysis workflow starts.
- [ ] Path filtering behaves correctly.
- [ ] Analysis completes without timeout.
- [ ] SARIF uploads to the Security tab.
- [ ] Required check behavior matches branch protection.
- [ ] Findings are actionable.

### Verify SARIF Upload

Check GitHub Security tab:

- [ ] Navigate to repository -> Security -> Code scanning alerts.
- [ ] Verify CodeQL results appear.
- [ ] Check alert detail pages for file, line, rule, severity, and guidance.
- [ ] Verify dismissal requires a reason.

### Validate Performance

| Path | Target | Actual | Status |
|------|--------|--------|--------|
| Tier 1 CI/CD analysis | 300 seconds or less | ______ | [ ] PASS |
| Tier 2 local full scan | 60 seconds or less | ______ | [ ] PASS |
| Tier 2 local quick scan | 60 seconds or less | ______ | [ ] PASS |
| Cache reuse with `--use-cache` | Faster than rebuild | ______ | [ ] PASS |

If timeouts occur:

- [ ] Confirm the scan used the intended language list.
- [ ] Confirm the config path is correct.
- [ ] Run diagnostics.
- [ ] Review `.codeql/results` and workflow logs.
- [ ] Use quick scan for local iteration, not as a replacement for CI.

```bash
python3 .codeql/scripts/get_codeql_diagnostics.py --output-format markdown
```

### Collect Developer Feedback

Ask builders:

- [ ] Was CLI installation clear?
- [ ] Did local scan output identify the next action?
- [ ] Did quick scan feel fast enough for active development?
- [ ] Did CI findings provide enough location and rule context?
- [ ] Were false positives rare enough to keep trust?

---

## Success Criteria

Mark rollout successful when all applicable criteria pass.

### Functional Criteria

- [ ] `python3 .codeql/scripts/test_codeql_rollout.py --ci` exits 0.
- [ ] `python3 .codeql/scripts/test_codeql_config.py --ci` exits 0.
- [ ] `python3 .codeql/scripts/invoke_codeql_scan.py --languages python actions` completes without scan execution errors.
- [ ] First production PR shows a CodeQL status check.
- [ ] SARIF appears in the GitHub Security tab.
- [ ] At least one developer or agent runs a local scan.
- [ ] `/codeql-scan` skill loads and reaches the scan path.

### Performance Criteria

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| CI analysis budget | 300 seconds or less | ______ | [ ] |
| Local full scan budget | 60 seconds or less | ______ | [ ] |
| Local quick scan budget | 60 seconds or less | ______ | [ ] |
| Cache reuse | Faster than rebuild | ______ | [ ] |
| False positive rate | Below 20 percent | ______ | [ ] |

### Adoption Criteria

- [ ] CodeQL docs are linked from the rollout PR.
- [ ] At least one maintainer knows how to run the local scan.
- [ ] At least one maintainer knows where SARIF appears in GitHub.
- [ ] No rollout issue blocks unrelated PRs.

### Quality Criteria

- [ ] Docs mention the two live tiers only.
- [ ] Docs point to Python scripts only.
- [ ] Quick scan is documented as on-demand.
- [ ] Automatic edit-time scanning is described only as retired.
- [ ] ADR-041 and ADR-042 references are current.

---

## Rollback Plan

Use the smallest rollback that restores developer flow.

### Immediate Rollback: CI Blocking Incorrectly

If CodeQL blocks PRs because of workflow failure or bad configuration:

```bash
gh workflow disable codeql-analysis.yml
```

Then open a fix PR for the workflow or config. Keep local scanning available while CI is disabled.

### Partial Rollback: Keep Local Scans Only

- [ ] Disable the CodeQL workflow with `gh workflow disable codeql-analysis.yml`.
- [ ] Keep `.codeql/scripts/` for local scans.
- [ ] Keep `.github/codeql/` for config validation and local scan consistency.
- [ ] Keep `.claude/skills/codeql-scan/` for on-demand agent use.
- [ ] Document the reason in the rollback PR.

### Full Rollback

Only use full rollback if both CI and local scanning are broken and cannot be fixed quickly.

Move affected paths to a reviewed backup branch or restore them with git from the last known good commit. Do not delete local work with unsafe shell commands.

Paths involved:

- `.github/workflows/codeql-analysis.yml`
- `.github/workflows/test-codeql-integration.yml`
- `.github/codeql/`
- `.codeql/scripts/`
- `.claude/skills/codeql-scan/`

Rollback PR checklist:

- [ ] Explain why rollback is needed.
- [ ] Link the failing workflow run or local diagnostic output.
- [ ] State which tier remains available, if any.
- [ ] State the forward-fix plan.

---

## Related Documentation

- **User Guide**: [docs/codeql-integration.md](./codeql-integration.md)
- **Architecture**: [docs/codeql-architecture.md](./codeql-architecture.md)
- **ADR-041**: [.agents/architecture/ADR-041-codeql-integration.md](../.agents/architecture/ADR-041-codeql-integration.md)
- **ADR-042**: [.agents/architecture/ADR-042-python-migration-strategy.md](../.agents/architecture/ADR-042-python-migration-strategy.md)
- **Rollout Validator**: [.codeql/scripts/test_codeql_rollout.py](../.codeql/scripts/test_codeql_rollout.py)

---

## Notes

**Rollout Date**: _______________

**Performed By**: _______________

**Approver**: _______________

**Issues Encountered**:

---

**Final Status**: [ ] SUCCESS [ ] PARTIAL [ ] ROLLBACK

**Completion Date**: _______________
