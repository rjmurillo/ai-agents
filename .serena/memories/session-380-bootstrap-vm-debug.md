# Session 380 - bootstrap-vm npm PATH fix

- Updated `scripts/bootstrap-vm.sh` to avoid `sudo npm` PATH loss when npm is installed via nvm.
- Install markdownlint-cli2 by using `npm` directly when running as root or preserving PATH via `sudo env PATH="$PATH"`.
- Added guard to error clearly if npm is missing.

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
