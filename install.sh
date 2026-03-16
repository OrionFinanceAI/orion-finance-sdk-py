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

# ─── default Sepolia RPC endpoints (tried in order until one works) ────────────

DEFAULT_RPC_1="https://1rpc.io/sepolia"
DEFAULT_RPC_2="https://0xrpc.io/sep"
DEFAULT_RPC_3="https://ethereum-sepolia-rpc.publicnode.com"

# Test if an RPC URL responds to eth_blockNumber.
rpc_works() {
    url="$1"
    if has curl; then
        resp=$(curl -sSf -m 5 -X POST -H "Content-Type: application/json" \
            --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
            "$url" 2>/dev/null) || return 1
    else
        resp=$(wget -qO- --timeout=5 --post-data='{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
            --header="Content-Type: application/json" "$url" 2>/dev/null) || return 1
    fi
    case "$resp" in *result*) return 0 ;; *) return 1 ;; esac
}

# Try default RPCs in order; echo first that works, or empty.
pick_default_rpc() {
    log "Trying default Sepolia RPCs..."
    if rpc_works "$DEFAULT_RPC_1"; then log_ok "Using $DEFAULT_RPC_1"; echo "$DEFAULT_RPC_1"; return; fi
    if rpc_works "$DEFAULT_RPC_2"; then log_ok "Using $DEFAULT_RPC_2"; echo "$DEFAULT_RPC_2"; return; fi
    if rpc_works "$DEFAULT_RPC_3"; then log_ok "Using $DEFAULT_RPC_3"; echo "$DEFAULT_RPC_3"; return; fi
    log_err "None of the default RPCs responded. You can set RPC_URL manually in .env later."
    echo ""
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
            log "Skipped. Create .env manually with: RPC_URL, MANAGER_PRIVATE_KEY, STRATEGIST_PRIVATE_KEY."
            log "Run 'orion' when ready. Docs: https://sdk.orionfinance.ai/"
            echo "" >&2
            return
            ;;
    esac

    env_file="./.env"
    if [ -f "$env_file" ]; then
        log ".env already exists — leaving it untouched."
        echo "" >&2
        return
    fi

    # ─── RPC_URL ───────────────────────────────────────────────────────────
    echo "" >&2
    log "RPC_URL (Sepolia or mainnet):"
    log "  [1] Use default (we try: 1rpc.io → 0xrpc.io → publicnode)"
    log "  [2] Paste your own URL"
    printf "  Choice [1/2]: " >&2
    read -r rpc_choice < /dev/tty || rpc_choice="1"

    rpc_url=""
    case "$rpc_choice" in
        2)
            printf "  RPC_URL=(paste here): " >&2
            read -r rpc_url < /dev/tty
            [ -n "$rpc_url" ] || { log_err "RPC_URL cannot be empty."; rpc_url=""; }
            ;;
        *)
            rpc_url=$(pick_default_rpc)
            ;;
    esac

    # ─── MANAGER_PRIVATE_KEY (required) ─────────────────────────────────────
    echo "" >&2
    while [ -z "$manager_key" ]; do
        printf "  MANAGER_PRIVATE_KEY=(paste here, required): " >&2
        read -r manager_key < /dev/tty
        [ -n "$manager_key" ] || log_err "Private key is required. Try again."
    done

    # ─── STRATEGIST_PRIVATE_KEY (optional, default same as manager) ──────────
    printf "  STRATEGIST_PRIVATE_KEY=(paste here, or Enter = same as manager): " >&2
    read -r strategist_key < /dev/tty
    [ -n "$strategist_key" ] || strategist_key="$manager_key"

    # ─── write .env ─────────────────────────────────────────────────────────
    {
        echo "# Orion Finance SDK — Environment Variables"
        echo "# Docs: https://sdk.orionfinance.ai/"
        echo ""
        echo "# RPC URL for blockchain connection"
        [ -n "$rpc_url" ] && echo "RPC_URL=$rpc_url" || echo "RPC_URL="
        echo ""
        echo "# Chain ID (default: 11155111 = Sepolia)"
        echo "# CHAIN_ID=11155111"
        echo ""
        echo "# Private key for manager operations"
        echo "MANAGER_PRIVATE_KEY=$manager_key"
        echo ""
        echo "# Private key for strategist operations"
        echo "STRATEGIST_PRIVATE_KEY=$strategist_key"
        echo ""
        echo "# Vault address — set after running: orion deploy-vault"
        echo "# ORION_VAULT_ADDRESS="
    } > "$env_file"

    log_ok ".env created at $env_file"

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
