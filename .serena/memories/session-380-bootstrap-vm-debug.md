# Session 380 - bootstrap-vm npm PATH fix

- Updated `scripts/bootstrap-vm.sh` to avoid `sudo npm` PATH loss when npm is installed via nvm.
- Install markdownlint-cli2 by using `npm` directly when running as root or preserving PATH via `sudo env PATH="$PATH"`.
- Added guard to error clearly if npm is missing.
