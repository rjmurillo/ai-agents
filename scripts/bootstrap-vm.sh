#!/usr/bin/env bash
# Bootstrap Ubuntu VM for ai-agents repository (DROID/Factory.ai)
# Usage: GH_TOKEN=<pat> ./bootstrap-vm.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "=== System Prerequisites ==="
sudo apt-get update -qq
sudo apt-get install -y -qq curl wget git jq unzip apt-transport-https \
    ca-certificates gnupg software-properties-common build-essential

echo "=== Node.js LTS ==="
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y -qq nodejs
fi
node --version && npm --version

echo "=== PowerShell Core ==="
if ! command -v pwsh &>/dev/null; then
    source /etc/os-release
    wget -q "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb" -O /tmp/ms.deb
    sudo dpkg -i /tmp/ms.deb && rm /tmp/ms.deb
    sudo apt-get update -qq && sudo apt-get install -y -qq powershell
fi
pwsh --version

echo "=== GitHub CLI ==="
if ! command -v gh &>/dev/null; then
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
        sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
        sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    sudo apt-get update -qq && sudo apt-get install -y -qq gh
fi
gh --version

[[ -n "${GITHUB_TOKEN:-}" ]] && export GH_TOKEN="$GITHUB_TOKEN"

echo "=== Python uv ==="
if ! command -v uv &>/dev/null && [[ ! -f "$HOME/.local/bin/uv" ]]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"

echo "=== markdownlint-cli2 ==="
if ! command -v markdownlint-cli2 &>/dev/null; then
    if command -v npm &>/dev/null; then
        NPM_PATH=$(command -v npm)

        # Check if npm is from nvm (user-writable prefix)
        NPM_PREFIX=$(npm config get prefix 2>/dev/null || echo "")

        if [[ "$(id -u)" -eq 0 ]]; then
            # Running as root - use npm directly with absolute path
            "$NPM_PATH" install -g markdownlint-cli2
        elif [[ "$NPM_PREFIX" =~ \.nvm ]]; then
            # nvm installation - prefix is user-writable, no sudo needed
            "$NPM_PATH" install -g markdownlint-cli2
        else
            # System npm - use sudo with safe PATH and absolute npm path
            NPM_DIR=$(dirname "$NPM_PATH")
            SAFE_PATH="${NPM_DIR}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            sudo env "PATH=$SAFE_PATH" "$NPM_PATH" install -g markdownlint-cli2
        fi
    else
        echo "npm not found. Please install Node.js (which includes npm) from https://nodejs.org or via your package manager, then re-run this script to complete markdownlint setup." >&2
        exit 1
    fi
fi

echo "=== Pester ==="
pwsh -NoProfile -Command '
    Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
    Install-Module -Name Pester -RequiredVersion 5.7.1 -Force -Scope CurrentUser
'

echo "=== powershell-yaml ==="
pwsh -NoProfile -Command 'Install-Module -Name powershell-yaml -Force -Scope CurrentUser -EA SilentlyContinue' 2>/dev/null || true

echo "=== Git Hooks ==="
[[ -d ".githooks" ]] && git config core.hooksPath .githooks

echo "=== Environment ==="
grep -q 'SKIP_AUTOFIX' "$HOME/.bashrc" 2>/dev/null || echo 'export SKIP_AUTOFIX=0' >> "$HOME/.bashrc"
export SKIP_AUTOFIX=0

echo "=== Done ==="
