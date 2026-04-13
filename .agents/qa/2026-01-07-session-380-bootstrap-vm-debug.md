# QA Report - Session 380 (bootstrap-vm.sh)

## Summary

Validated the markdownlint install flow in `scripts/bootstrap-vm.sh` to avoid `sudo npm` PATH issues when Node.js is installed via nvm.

## Test Strategy

- **Manual review**: Confirmed logic branches for root vs non-root execution.
- **Automated tests**: Not run (script change only).

## Results

- ✅ Logic guards for missing npm and PATH preservation when using sudo.
- ⚠️ No automated tests executed.

## Notes

If future CI covers shell scripts, add a smoke test that runs `bootstrap-vm.sh` in a container with nvm-installed Node.
