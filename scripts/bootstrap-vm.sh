#!/usr/bin/env bash
# Bootstrap Ubuntu VM for ai-agents repository (DROID/Factory.ai)
# Usage: GH_TOKEN=<pat> ./bootstrap-vm.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "=== System Prerequisites ==="
sudo apt-get update -qq
sudo apt-get install -y -qq curl wget git jq unzip zstd apt-transport-https \
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

echo "=== pyenv (Python 3.12.8) ==="
# Python 3.13.7 has a critical bug breaking CodeQL and skill validation
# Ubuntu 25.10 has no packages for 3.12.x, so we use pyenv
if ! command -v pyenv &>/dev/null; then
    # Install build dependencies for Python compilation
    sudo apt-get install -y -qq build-essential libssl-dev zlib1g-dev \
        libbz2-dev libreadline-dev libsqlite3-dev curl git \
        libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

    # Install pyenv
    curl https://pyenv.run | bash

    # Add pyenv to PATH for this session
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"

    # Add pyenv to shell config for future sessions
    # Detect shell and update appropriate config file
    SHELL_CONFIG=""
    if [[ -n "$ZSH_VERSION" ]] || [[ "$SHELL" == *"zsh"* ]]; then
        SHELL_CONFIG="$HOME/.zshrc"
    elif [[ -n "$BASH_VERSION" ]] || [[ "$SHELL" == *"bash"* ]]; then
        SHELL_CONFIG="$HOME/.bashrc"
    else
        # Default to bashrc if shell cannot be detected
        SHELL_CONFIG="$HOME/.bashrc"
    fi

    # Only add if not already present
    if ! grep -q "PYENV_ROOT" "$SHELL_CONFIG" 2>/dev/null; then
        {
            echo ''
            echo '# pyenv'
            echo 'export PYENV_ROOT="$HOME/.pyenv"'
            echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"'
            echo 'eval "$(pyenv init -)"'
        } >> "$SHELL_CONFIG"
        echo "Added pyenv configuration to $SHELL_CONFIG"
    fi
fi

# Ensure pyenv is available
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv &>/dev/null; then
    eval "$(pyenv init -)"
fi

# Install Python 3.12.8
if ! pyenv versions --bare | grep -q "^3.12.8$"; then
    echo "Installing Python 3.12.8 via pyenv (this may take a few minutes)..."
    pyenv install 3.12.8
fi

# Set Python 3.12.8 as the local version for this project
if [[ -d ".git" ]]; then
    pyenv local 3.12.8
    echo "Python 3.12.8 set as local version (.python-version file created)"
fi

python3 --version

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
