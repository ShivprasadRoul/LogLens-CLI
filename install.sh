#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# LogLens — Installer
# AI-Powered Log Intelligence CLI
#
# Supports: macOS (Homebrew), Ubuntu/Debian (apt), Arch Linux (pacman)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/install.sh | bash
#   — or —
#   bash install.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET} $*"; }
info() { echo -e "${BLUE}→${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }
step() { echo -e "\n${BOLD}$*${RESET}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e ""
echo -e "${BOLD}${BLUE}  ██╗      ██████╗  ██████╗ ██╗     ███████╗███╗   ██╗███████╗${RESET}"
echo -e "${BOLD}${BLUE}  ██║     ██╔═══██╗██╔════╝ ██║     ██╔════╝████╗  ██║██╔════╝${RESET}"
echo -e "${BOLD}${BLUE}  ██║     ██║   ██║██║  ███╗██║     █████╗  ██╔██╗ ██║███████╗${RESET}"
echo -e "${BOLD}${BLUE}  ██║     ██║   ██║██║   ██║██║     ██╔══╝  ██║╚██╗██║╚════██║${RESET}"
echo -e "${BOLD}${BLUE}  ███████╗╚██████╔╝╚██████╔╝███████╗███████╗██║ ╚████║███████║${RESET}"
echo -e "${BOLD}${BLUE}  ╚══════╝ ╚═════╝  ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝${RESET}"
echo -e "${DIM}  AI-Powered Log Intelligence CLI${RESET}"
echo -e ""

LOGLENS_DIR="${HOME}/.loglens"
INSTALL_DIR="${LOGLENS_DIR}/install"
BIN_DIR="${HOME}/.local/bin"

# ── 1. Detect OS ──────────────────────────────────────────────────────────────
step "1. Detecting operating system..."

OS=""
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    ok "macOS detected"
elif [[ -f /etc/os-release ]]; then
    source /etc/os-release
    case "$ID" in
        ubuntu|debian|linuxmint|pop) OS="debian" ;;
        arch|manjaro|endeavouros)    OS="arch" ;;
        *)
            if command -v apt-get &>/dev/null; then OS="debian"
            elif command -v pacman &>/dev/null;  then OS="arch"
            else fail "Unsupported Linux distribution: $ID. Install jq and uv manually, then run: uv tool install loglens"
            fi
            ;;
    esac
    ok "Linux detected ($ID)"
else
    fail "Unsupported OS. Please install manually: https://github.com/ShivprasadRoul/LogLens#manual-install"
fi

# ── 2. Install jq ─────────────────────────────────────────────────────────────
step "2. Checking for jq (required system dependency)..."

if command -v jq &>/dev/null; then
    JQ_VERSION=$(jq --version 2>&1)
    ok "jq already installed ($JQ_VERSION)"
else
    info "Installing jq..."
    case "$OS" in
        macos)
            if ! command -v brew &>/dev/null; then
                fail "Homebrew is required to install jq on macOS.\nInstall Homebrew first: https://brew.sh\nThen re-run this installer."
            fi
            brew install jq
            ;;
        debian)
            sudo apt-get update -qq && sudo apt-get install -y jq
            ;;
        arch)
            sudo pacman -Sy --noconfirm jq
            ;;
    esac

    if ! command -v jq &>/dev/null; then
        fail "jq installation failed. Please install it manually:\n  macOS: brew install jq\n  Ubuntu: sudo apt install jq\n  Arch:   sudo pacman -S jq"
    fi
    ok "jq installed ($(jq --version))"
fi

# ── 3. Check Python ───────────────────────────────────────────────────────────
step "3. Checking Python version..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VERSION=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
        if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 9 ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo ""
    warn "Python 3.9+ not found. Installing via system package manager..."
    case "$OS" in
        macos)   brew install python@3.11 && PYTHON="python3" ;;
        debian)  sudo apt-get install -y python3 python3-pip && PYTHON="python3" ;;
        arch)    sudo pacman -Sy --noconfirm python && PYTHON="python3" ;;
    esac
    [[ -z "$PYTHON" ]] && fail "Could not install Python. Please install Python 3.9+ manually."
fi

ok "Python $PY_VERSION found ($PYTHON)"

# ── 4. Install uv ─────────────────────────────────────────────────────────────
step "4. Checking for uv (package manager)..."

if command -v uv &>/dev/null; then
    ok "uv already installed ($(uv --version))"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for this session
    export PATH="${HOME}/.cargo/bin:${HOME}/.local/bin:${PATH}"
    if ! command -v uv &>/dev/null; then
        fail "uv installation failed. Install manually: https://docs.astral.sh/uv/getting-started/installation/"
    fi
    ok "uv installed ($(uv --version))"
fi

# ── 5. Clone / update LogLens ─────────────────────────────────────────────────
step "5. Installing LogLens..."

mkdir -p "$INSTALL_DIR"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Updating existing LogLens installation..."
    git -C "$INSTALL_DIR" pull --ff-only origin main
    ok "LogLens updated"
else
    info "Cloning LogLens from GitHub..."
    git clone --depth 1 https://github.com/ShivprasadRoul/LogLens.git "$INSTALL_DIR"
    ok "LogLens cloned"
fi

# ── 6. Install Python dependencies ────────────────────────────────────────────
step "6. Installing Python dependencies..."

cd "$INSTALL_DIR"
uv sync --quiet
ok "Dependencies installed"

# ── 7. Create loglens wrapper script ─────────────────────────────────────────
step "7. Creating loglens CLI entry point..."

mkdir -p "$BIN_DIR"

WRAPPER="${BIN_DIR}/loglens"
cat > "$WRAPPER" << WRAPPER_SCRIPT
#!/usr/bin/env bash
# LogLens CLI wrapper — auto-generated by install.sh
exec uv run --project "${INSTALL_DIR}" python -m loglens.cli "\$@"
WRAPPER_SCRIPT

chmod +x "$WRAPPER"
ok "Created: $WRAPPER"

# ── 8. Add ~/.local/bin to PATH ───────────────────────────────────────────────
step "8. Configuring PATH..."

SHELL_RC=""
case "$SHELL" in
    */zsh)  SHELL_RC="${HOME}/.zshrc" ;;
    */bash) SHELL_RC="${HOME}/.bashrc" ;;
    */fish) SHELL_RC="${HOME}/.config/fish/config.fish" ;;
    *)      SHELL_RC="${HOME}/.profile" ;;
esac

PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
FISH_PATH_LINE='fish_add_path $HOME/.local/bin'

if [[ "$SHELL" == */fish ]]; then
    if ! grep -qF "fish_add_path \$HOME/.local/bin" "$SHELL_RC" 2>/dev/null; then
        echo "$FISH_PATH_LINE" >> "$SHELL_RC"
        info "Added ~/.local/bin to PATH in $SHELL_RC"
    fi
else
    if ! grep -qF "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# LogLens CLI" >> "$SHELL_RC"
        echo "$PATH_LINE" >> "$SHELL_RC"
        info "Added ~/.local/bin to PATH in $SHELL_RC"
    fi
fi

export PATH="${BIN_DIR}:${PATH}"
ok "PATH configured"

# ── 9. API key setup ──────────────────────────────────────────────────────────
step "9. API key setup..."

echo ""
echo -e "${DIM}LogLens supports multiple LLM providers. You can set keys now or later${RESET}"
echo -e "${DIM}with: loglens config set-key <provider> <key>${RESET}"
echo ""
echo -e "  Providers: ${BOLD}openai${RESET}, anthropic, groq, gemini"
echo ""

read -rp "$(echo -e "${BOLD}Enter your OpenAI API key${RESET} (or press Enter to skip): ")" OPENAI_KEY
if [[ -n "$OPENAI_KEY" ]]; then
    cd "$INSTALL_DIR"
    uv run python -m loglens.cli config set-key openai "$OPENAI_KEY" 2>/dev/null && \
        ok "OpenAI API key saved to ~/.loglens/config.json" || \
        warn "Could not save key automatically. Run: loglens config set-key openai <key>"
fi

# ── 10. Verify installation ───────────────────────────────────────────────────
step "10. Verifying installation..."

if "${BIN_DIR}/loglens" --help &>/dev/null; then
    ok "loglens CLI is working"
else
    warn "Could not verify loglens. You may need to reload your shell."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}${GREEN}  LogLens installed successfully!${RESET}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${BOLD}Quick Start:${RESET}"
echo ""
echo -e "  ${CYAN:-\033[0;36m}# Reload your shell to pick up PATH changes${RESET}"
echo -e "  ${CYAN:-\033[0;36m}source ${SHELL_RC}${RESET}"
echo ""
echo -e "  ${CYAN:-\033[0;36m}# Ingest a log file${RESET}"
echo -e "  ${BOLD}loglens ingest myapp.log${RESET}"
echo ""
echo -e "  ${CYAN:-\033[0;36m}# Ask a question${RESET}"
echo -e "  ${BOLD}loglens query myapp --query \"what caused the most errors?\"${RESET}"
echo ""
echo -e "  ${CYAN:-\033[0;36m}# Start interactive chat${RESET}"
echo -e "  ${BOLD}loglens chat myapp${RESET}"
echo ""
echo -e "  ${DIM}Docs: https://github.com/ShivprasadRoul/LogLens${RESET}"
echo ""

# Prompt to reload shell
if [[ "${SHELL}" == */zsh ]]; then
    echo -e "${DIM}Run: source ~/.zshrc${RESET}"
elif [[ "${SHELL}" == */bash ]]; then
    echo -e "${DIM}Run: source ~/.bashrc${RESET}"
fi
echo ""
