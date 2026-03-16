#!/bin/sh
# Orion Finance SDK installer
# Usage: curl -sSfL https://raw.githubusercontent.com/OrionFinanceAI/orion-finance-sdk-py/dev/install.sh | sh
#
# Environment variables:
#   VERSION     — specific version to install (default: latest from PyPI)
#   INSTALL_DIR — override directory to put the 'orion' binary (default: auto-detected)

set -e

PACKAGE="orion-finance-sdk-py"
BINARY="orion"
PYTHON_VERSION="3.13"

# ─── helpers ──────────────────────────────────────────────────────────────────

log()     { printf "  %s\n" "$*" >&2; }
log_ok()  { printf "  ✓ %s\n" "$*" >&2; }
log_err() { printf "  ✗ %s\n" "$*" >&2; }
err()     { log_err "$*"; exit 1; }
has()     { command -v "$1" > /dev/null 2>&1; }
has_tty() { [ -t 0 ] || [ -t 1 ] || [ -t 2 ]; }

# ─── step 1: ensure uv is installed ──────────────────────────────────────────

ensure_uv() {
    if has uv; then
        log_ok "uv already installed ($(uv --version 2>/dev/null | head -1))"
        return
    fi

    log "uv not found — installing it now..."

    if has curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif has wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        err "curl or wget is required to install uv. Please install one and retry."
    fi

    # The uv installer drops the binary in ~/.local/bin or ~/.cargo/bin.
    # Source the env update it prints, or find the binary manually.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! has uv; then
        err "uv installation succeeded but 'uv' is still not on PATH.
       Open a new shell and re-run this script, or add the above directories to PATH."
    fi

    log_ok "uv installed successfully ($(uv --version 2>/dev/null | head -1))"
}

# ─── step 2: resolve latest version from PyPI ────────────────────────────────

resolve_version() {
    if [ -n "$VERSION" ]; then
        echo "$VERSION"
        return
    fi

    if has curl; then
        curl -sSfL "https://pypi.org/pypi/${PACKAGE}/json" \
            | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
            | head -1
    elif has wget; then
        wget -qO- "https://pypi.org/pypi/${PACKAGE}/json" \
            | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
            | head -1
    fi
}

# ─── step 3: install the SDK ─────────────────────────────────────────────────

install_sdk() {
    version="$1"

    # uv tool install handles:
    #   - downloading Python 3.13 if not present
    #   - creating an isolated virtual environment
    #   - placing the 'orion' binary on PATH
    uv tool install "${PACKAGE}==${version}" \
        --python "${PYTHON_VERSION}" \
        --force-reinstall \
        ${INSTALL_DIR:+--bin-dir "$INSTALL_DIR"}

    log_ok "${PACKAGE} ${version} installed"
}

# ─── step 4: verify the binary is reachable ──────────────────────────────────

verify_binary() {
    # uv adds its tool bin dir to PATH — make sure it's available in this shell too
    uv_tool_bin="$(uv tool dir --bin 2>/dev/null)" || true
    if [ -n "$uv_tool_bin" ]; then
        export PATH="${uv_tool_bin}:${PATH}"
    fi

    if has "$BINARY"; then
        log_ok "'${BINARY}' is on PATH: $(command -v "$BINARY")"
        return
    fi

    # Binary installed but shell PATH not updated yet
    echo "" >&2
    log "⚠  '${BINARY}' was installed but is not yet on your PATH."
    log "   Add uv's tool bin directory to your shell profile:"
    echo "" >&2
    log "   bash/zsh:  echo 'export PATH=\"\$(uv tool dir --bin):\$PATH\"' >> ~/.zshrc"
    log "   fish:      fish_add_path \$(uv tool dir --bin)"
    echo "" >&2
    log "   Then run:  source ~/.zshrc  (or open a new terminal)"
}

# ─── step 5: interactive post-install setup ──────────────────────────────────

post_install() {
    version="$1"
    echo "" >&2
    log "────────────────────────────────────────────"
    log " Orion Finance SDK ${version} — ready!"
    log "────────────────────────────────────────────"
    echo "" >&2

    log "The SDK reads your config from a .env file."
    printf "  Create .env in the current directory now? [Y/n] " >&2
    read -r answer < /dev/tty || answer=""

    case "$answer" in
        [nN]*)
            echo "" >&2
            log "Skipped. Required .env keys:"
            log "   RPC_URL                — your Sepolia/mainnet RPC endpoint"
            log "   MANAGER_PRIVATE_KEY    — manager wallet private key"
            log "   STRATEGIST_PRIVATE_KEY — strategist wallet private key"
            log "   ORION_VAULT_ADDRESS    — set after running 'orion deploy-vault'"
            ;;
        *)
            env_file="./.env"
            if [ -f "$env_file" ]; then
                log ".env already exists — leaving it untouched."
            else
                cat > "$env_file" << 'EOF'
# Orion Finance SDK — Environment Variables
# Docs: https://sdk.orionfinance.ai/

# RPC URL for blockchain connection
RPC_URL=

# Chain ID (default: 11155111 = Sepolia)
# CHAIN_ID=11155111

# Private key for manager operations
MANAGER_PRIVATE_KEY=

# Private key for strategist operations (can be same as manager)
STRATEGIST_PRIVATE_KEY=

# Vault address — populated after running: orion deploy-vault
# ORION_VAULT_ADDRESS=
EOF
                log_ok ".env created — fill in RPC_URL and your private keys before use."
            fi
            ;;
    esac

    echo "" >&2
    log "Get started:"
    log "   orion                  — interactive menu"
    log "   orion deploy-vault     — deploy a new vault"
    log "   orion --help           — all commands"
    echo "" >&2
    log "Docs: https://sdk.orionfinance.ai/"
    echo "" >&2
}

# ─── main ─────────────────────────────────────────────────────────────────────

main() {
    if ! has curl && ! has wget; then
        err "curl or wget is required. Please install one and retry."
    fi

    echo "" >&2
    log "Installing Orion Finance SDK..."
    echo "" >&2

    ensure_uv

    version=$(resolve_version)
    [ -n "$version" ] || err "could not resolve latest version from PyPI"

    log "Resolved latest version: ${version}"
    echo "" >&2

    install_sdk "$version"

    verify_binary

    if has_tty; then
        post_install "$version"
    else
        echo "" >&2
        log "Orion Finance SDK ${version} installed."
        log "Run 'orion' to launch the interactive CLI."
        log "Run 'orion --help' for all commands."
        log "Docs: https://sdk.orionfinance.ai/"
        echo "" >&2
    fi
}

main "$@"
