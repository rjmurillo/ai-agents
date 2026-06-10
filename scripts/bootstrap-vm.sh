#!/usr/bin/env bash
# Bootstrap Ubuntu VM for ai-agents repository (DROID/Factory.ai)
# Usage: GH_TOKEN=<pat> ./bootstrap-vm.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Anchor to the repository root so relative paths (.python-version, uv.lock,
# pyproject.toml, .githooks) resolve correctly regardless of the caller's CWD
# (CWE-22 defense: never resolve repo paths against an attacker-influenced CWD).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Bound every outbound download: a hung mirror must fail the step, not hang
# the SessionStart hook. Retries are only safe on curls that write to a file
# (-o); a --retry on a piped transfer can re-send bytes mid-stream.
CURL_OPTS=(--connect-timeout 10 --max-time 300)
CURL_RETRY_OPTS=("${CURL_OPTS[@]}" --retry 3 --retry-delay 5)

install_uv() {
    # Download then execute (not curl|sh) so a partial transfer never
    # reaches the shell and retries are safe.
    local installer
    installer="$(mktemp)"
    curl "${CURL_RETRY_OPTS[@]}" -LsSf https://astral.sh/uv/install.sh -o "$installer"
    sh "$installer"
    rm -f "$installer"
}

echo "=== System Prerequisites ==="
sudo apt-get update -qq
sudo apt-get install -y -qq curl wget git jq unzip zstd apt-transport-https \
    ca-certificates gnupg software-properties-common build-essential

echo "=== Node.js LTS ==="
if ! command -v node &>/dev/null; then
    # Signed keyring + explicit apt repo instead of piping the NodeSource
    # setup script into root bash (semgrep curl-pipe-bash: a MITM'd response
    # would execute as root). NODE_MAJOR pins the current LTS line because
    # NodeSource publishes no rolling LTS path (node_lts.x returns 404).
    NODE_MAJOR=22
    curl "${CURL_RETRY_OPTS[@]}" -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key -o /tmp/nodesource.gpg
    sudo gpg --yes --dearmor -o /usr/share/keyrings/nodesource.gpg /tmp/nodesource.gpg
    rm -f /tmp/nodesource.gpg
    echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" | \
        sudo tee /etc/apt/sources.list.d/nodesource.list >/dev/null
    sudo apt-get update -qq
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
    curl "${CURL_OPTS[@]}" -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
        sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
        sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    sudo apt-get update -qq && sudo apt-get install -y -qq gh
fi
gh --version

[[ -n "${GITHUB_TOKEN:-}" ]] && export GH_TOKEN="$GITHUB_TOKEN"

echo "=== Python uv ==="
export PATH="$HOME/.local/bin:$PATH"
# Single source of truth for the interpreter version is the committed
# .python-version pin. Do not hardcode interpreter versions in this script;
# bump the pin instead.
PYTHON_PIN=""
if [[ -f ".python-version" ]]; then
    PYTHON_PIN="$(tr -d '[:space:]' < .python-version)"
fi

# Container images can ship a uv too old to know the pinned interpreter
# (uv 0.8.17 predates the CPython 3.14.x downloads). Detect by capability,
# not version compare: ask uv to resolve the pin against its download list,
# and re-run the standalone installer when it cannot. Never use
# `uv self update` here: that path queries the GitHub API and gets
# rate-limited on shared container egress IPs.
if ! command -v uv &>/dev/null; then
    install_uv
elif [[ -n "$PYTHON_PIN" ]] && ! uv python list "$PYTHON_PIN" 2>/dev/null | grep -q .; then
    echo "uv $(uv --version) cannot resolve Python ${PYTHON_PIN}; reinstalling latest uv"
    install_uv
fi
grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
uv --version

echo "=== Python ${PYTHON_PIN:-(no .python-version pin)} ==="
if [[ -n "$PYTHON_PIN" ]]; then
    # Prebuilt interpreter download (seconds). The previous pyenv source
    # compile took minutes and blew the SessionStart hook budget on Claude
    # web containers, so the steps after it never ran. --default links
    # python3/python into ~/.local/bin so bare python3 resolves to the
    # pinned interpreter.
    uv python install --default "$PYTHON_PIN"
fi
python3 --version

echo "=== Python Dependencies ==="
if [[ -f "uv.lock" ]]; then
    # Sync the project venv from the lockfile, dev extras included. The
    # pre-push gate (.githooks/pre-push) runs validation through
    # `uv run --frozen`, so .venv is the environment that must exist for a
    # push to validate without on-the-fly downloads.
    uv sync --frozen --extra dev
    echo "✓ Python dependencies synced into .venv (uv sync --frozen --extra dev)"

    # Put the project venv first on PATH for this run and future shells so
    # bare `python3 scripts/...` invocations (AGENTS.md, CI docs) resolve to
    # the synced environment. Installing project deps into the interpreter
    # itself is not an option: uv-managed interpreters are PEP 668
    # externally-managed and uv refuses to modify them. The venv is the one
    # environment that has the project deps.
    VENV_BIN="$(pwd)/.venv/bin"
    export PATH="$VENV_BIN:$PATH"
    grep -qF "$VENV_BIN" "$HOME/.bashrc" 2>/dev/null \
        || echo "export PATH=\"$VENV_BIN:\$PATH\"" >> "$HOME/.bashrc"

    # Verify key tools are available through the project environment
    if uv run --frozen ruff --version &>/dev/null; then
        echo "✓ ruff $(uv run --frozen ruff --version) available for Python linting"
    fi
    if uv run --frozen pytest --version &>/dev/null; then
        echo "✓ pytest $(uv run --frozen pytest --version 2>&1 | head -1) available for Python testing"
    fi
elif [[ -f "pyproject.toml" ]]; then
    echo "Installing Python dependencies from pyproject.toml..."
    # Non-fatal: when python3 resolves to a uv-managed interpreter this
    # fails under PEP 668 (externally managed), and `set -e` would abort
    # the rest of bootstrap. This repo always has uv.lock, so this branch
    # only serves forks or derivatives without a lockfile.
    if uv pip install --system -e ".[dev]"; then
        echo "✓ Python dependencies installed"
    else
        echo "⚠ uv pip install --system failed (PEP 668 externally-managed interpreter?); run 'uv venv && uv pip install -e .[dev]' instead"
    fi
else
    echo "⚠ No pyproject.toml found, skipping Python dependency installation"
fi

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
# Skip the PSGallery round-trip (~1-2 min) when the pinned version is already
# installed. The pin must match the Prerequisites in CONTRIBUTING.md.
PESTER_VERSION="5.7.1"
if pwsh -NoProfile -Command "if (Get-Module -ListAvailable -Name Pester | Where-Object Version -eq '$PESTER_VERSION') { exit 0 }; exit 1" &>/dev/null; then
    echo "Pester $PESTER_VERSION already installed; skipping"
else
    pwsh -NoProfile -Command "
        Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
        Install-Module -Name Pester -RequiredVersion $PESTER_VERSION -Force -Scope CurrentUser
    "
fi

echo "=== powershell-yaml ==="
if pwsh -NoProfile -Command 'if (Get-Module -ListAvailable -Name powershell-yaml) { exit 0 }; exit 1' &>/dev/null; then
    echo "powershell-yaml already installed; skipping"
else
    # Trust PSGallery here too: with the Pester install skipped on warm
    # containers, this branch can no longer rely on the Pester block having
    # set the policy first.
    pwsh -NoProfile -Command '
        Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
        Install-Module -Name powershell-yaml -Force -Scope CurrentUser -EA SilentlyContinue
    ' 2>/dev/null || true
fi

echo "=== Git Hooks ==="
[[ -d ".githooks" ]] && git config core.hooksPath .githooks
git config --global core.autocrlf input

echo "=== Linting Tools ==="
# actionlint: pinned to v1.7.11 with checksum verification
ACTIONLINT_VERSION="1.7.11"
if ! command -v actionlint &>/dev/null; then
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64)  AL_ARCH="amd64"; AL_SHA256="900919a84f2229bac68ca9cd4103ea297abc35e9689ebb842c6e34a3d1b01b0a" ;;
        aarch64) AL_ARCH="arm64"; AL_SHA256="21bc0dfb57a913fe175298c2a9e906ee630f747cb66d0a934d0d4b69f4ee1235" ;;
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
    esac
    AL_TARBALL="actionlint_${ACTIONLINT_VERSION}_linux_${AL_ARCH}.tar.gz"
    AL_URL="https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/${AL_TARBALL}"

    mkdir -p "$HOME/.local/bin"
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf -- "$TMP_DIR"' EXIT
    curl "${CURL_RETRY_OPTS[@]}" -fsSL "$AL_URL" -o "$TMP_DIR/$AL_TARBALL"
    echo "${AL_SHA256}  $TMP_DIR/$AL_TARBALL" | sha256sum --check --strict
    tar -xzf "$TMP_DIR/$AL_TARBALL" -C "$TMP_DIR" actionlint
    install -m 755 "$TMP_DIR/actionlint" "$HOME/.local/bin/actionlint"

    if ! command -v actionlint &>/dev/null; then
        echo "actionlint installation failed: binary not found on PATH" >&2
        exit 1
    fi
fi
if ! command -v yamllint &>/dev/null; then
    # `uv tool install` puts the yamllint shim into ~/.local/bin (on PATH);
    # a `uv pip install` into the uv-managed interpreter would land the
    # entry point in the interpreter's own bin dir, off PATH.
    uv tool install --quiet yamllint

    if ! command -v yamllint &>/dev/null; then
        echo "yamllint installation failed: binary not found on PATH" >&2
        exit 1
    fi
fi

echo "=== Environment ==="
grep -q 'SKIP_AUTOFIX' "$HOME/.bashrc" 2>/dev/null || echo 'export SKIP_AUTOFIX=0' >> "$HOME/.bashrc"
export SKIP_AUTOFIX=0

echo "=== Done ==="
