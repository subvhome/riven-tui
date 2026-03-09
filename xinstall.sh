#!/bin/sh

# Riven TUI - Universal Multi-OS Installer (Strict POSIX)
# Supports: Debian/Ubuntu, Alpine, Fedora, Arch, and macOS.

set -e

# --- Colors for Output (POSIX compatible) ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

printf "${BLUE}==========================================\n"
printf "      🚀 Riven TUI Universal Setup\n"
printf "==========================================${NC}\n"

# 1. OS Detection
printf "${YELLOW}[1/7] Detecting system environment...${NC}\n"

OS_TYPE="unknown"
PKG_MANAGER=""

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_TYPE=$ID
    if command -v apt-get >/dev/null 2>&1; then PKG_MANAGER="apt";
    elif command -v apk >/dev/null 2>&1; then PKG_MANAGER="apk";
    elif command -v dnf >/dev/null 2>&1; then PKG_MANAGER="dnf";
    elif command -v pacman >/dev/null 2>&1; then PKG_MANAGER="pacman"; fi
elif [ "$(uname)" = "Darwin" ]; then
    OS_TYPE="macos"
    PKG_MANAGER="brew"
fi

printf "${BLUE}Detected OS: ${CYAN}%s${NC} (via ${CYAN}%s${NC})\n" "$OS_TYPE" "$PKG_MANAGER"

# Check for sudo
SUDO_CMD=""
if command -v sudo >/dev/null 2>&1; then
    SUDO_CMD="sudo"
fi

# 2. Install System Dependencies
printf "${YELLOW}[2/7] Installing system dependencies...${NC}\n"

case $PKG_MANAGER in
    apt)
        $SUDO_CMD apt-get update && $SUDO_CMD apt-get install -y git python3 python3-venv chafa curl
        ;;
    apk)
        # Alpine needs build-base and python3-dev to compile some python packages
        $SUDO_CMD apk update && $SUDO_CMD apk add git python3 py3-pip chafa curl bash coreutils build-base python3-dev musl-dev
        ;;
    dnf)
        $SUDO_CMD dnf install -y git python3 chafa curl
        ;;
    pacman)
        $SUDO_CMD pacman -S --noconfirm git python chafa curl
        ;;
    brew)
        brew install git python chafa curl
        ;;
    *)
        printf "${RED}Error: Unsupported package manager. Please install git, python3, and chafa manually.${NC}\n"
        exit 1
        ;;
esac

# 3. Installation Directory
printf "${YELLOW}[3/7] Setting up installation directory...${NC}\n"
DEFAULT_DIR="$HOME/riven-tui"
printf "Where should I install Riven TUI? [Default: %s]: " "$DEFAULT_DIR"
read INPUT_DIR < /dev/tty
INSTALL_DIR=${INPUT_DIR:-$DEFAULT_DIR}

if [ -d "$INSTALL_DIR" ]; then
    printf "${YELLOW}Directory %s already exists.${NC}\n" "$INSTALL_DIR"
    printf "Overwrite? (y/N): "
    read OVERWRITE < /dev/tty
    case "$OVERWRITE" in
        [Yy]*) rm -rf "$INSTALL_DIR" ;;
        *) printf "${RED}Setup aborted.${NC}\n"; exit 1 ;;
    esac
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 4. Clone Repository
printf "${YELLOW}[4/7] Downloading Riven TUI...${NC}\n"
git clone https://github.com/subvhome/riven-tui.git .

# 5. Virtual Environment
printf "${YELLOW}[5/7] Setting up Python environment...${NC}\n"
python3 -m venv .venv
. ./.venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. Configuration Wizard
printf "\n${BLUE}--- Configuration Wizard ---${NC}\n"
printf "Riven API Key: "
read RIVEN_API_KEY < /dev/tty
printf "TMDB Bearer Token: "
read TMDB_TOKEN < /dev/tty

printf "Backend Host [localhost]: "
read RIVEN_HOST < /dev/tty
RIVEN_HOST=${RIVEN_HOST:-localhost}
printf "Backend Port [8080]: "
read RIVEN_PORT < /dev/tty
RIVEN_PORT=${RIVEN_PORT:-8080}

cat > settings.json <<EOF
{
    "riven_key": "$RIVEN_API_KEY",
    "tmdb_bearer_token": "$TMDB_TOKEN",
    "be_config": {
        "protocol": "http",
        "host": "$RIVEN_HOST",
        "port": $RIVEN_PORT
    },
    "request_timeout": 30.0,
    "log_display_limit": 50,
    "chafa_max_width": 100
}
EOF

# 7. Final Polish
printf "${YELLOW}[7/7] Finishing up...${NC}\n"

# Create the runner script
cat > run.sh <<EOF
#!/bin/bash
export COLORTERM=truecolor
APP_DIR="$INSTALL_DIR"
cd "\$APP_DIR"
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi
exec python3 riven_tui.py "\$@"
EOF
chmod +x run.sh

# Alias setup
printf "\n${BLUE}==========================================${NC}\n"
printf "${GREEN}      Setup Complete!${NC}\n"
printf "==========================================\n"

printf "Add 'riven-tui' alias to your shell profile? [y/N]: "
read ADD_ALIAS < /dev/tty
case "$ADD_ALIAS" in
    [Yy]*)
        SHELL_PROFILE=""
        case "$SHELL" in
            *zsh*) SHELL_PROFILE="$HOME/.zshrc" ;;
            *bash*) SHELL_PROFILE="$HOME/.bashrc" ;;
            *) SHELL_PROFILE="$HOME/.profile" ;;
        esac

        if [ -n "$SHELL_PROFILE" ]; then
            if ! grep -q "alias riven-tui=" "$SHELL_PROFILE" 2>/dev/null; then
                printf "\nalias riven-tui='%s/run.sh'\n" "$INSTALL_DIR" >> "$SHELL_PROFILE"
                printf "${GREEN}✓ Alias added to %s.${NC}\n" "$SHELL_PROFILE"
                printf "${YELLOW}Please restart your terminal or run: . %s${NC}\n" "$SHELL_PROFILE"
            fi
        fi
        ;;
esac

printf "\nStart the app anytime by typing: ${CYAN}riven-tui${NC}\n"
