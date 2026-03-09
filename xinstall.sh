#!/bin/bash

# Riven TUI - Universal Multi-OS Installer
# Supports: Debian/Ubuntu, Alpine, Fedora, Arch, and macOS.

set -e

# --- Colors for Output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}=========================================="
echo -e "      🚀 Riven TUI Universal Setup"
echo -e "==========================================${NC}"

# 1. OS Detection
echo -e "${YELLOW}[1/7] Detecting system environment...${NC}"

OS_TYPE="unknown"
PKG_MANAGER=""

if [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
    PKG_MANAGER="brew"
elif [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_TYPE=$ID
    if command -v apt-get &> /dev/null; then PKG_MANAGER="apt";
    elif command -v apk &> /dev/null; then PKG_MANAGER="apk";
    elif command -v dnf &> /dev/null; then PKG_MANAGER="dnf";
    elif command -v pacman &> /dev/null; then PKG_MANAGER="pacman"; fi
fi

echo -e "${BLUE}Detected OS: ${CYAN}$OS_TYPE${NC} (via ${CYAN}$PKG_MANAGER${NC})"

# 2. Install System Dependencies
echo -e "${YELLOW}[2/7] Installing system dependencies...${NC}"

case $PKG_MANAGER in
    apt)
        sudo apt-get update && sudo apt-get install -y git python3 python3-venv chafa curl
        ;;
    apk)
        # Alpine needs specific build tools for some python wheels
        sudo apk update && sudo apk add git python3 py3-pip chafa curl bash coreutils
        ;;
    dnf)
        sudo dnf install -y git python3 chafa curl
        ;;
    pacman)
        sudo pacman -S --noconfirm git python chafa curl
        ;;
    brew)
        brew install git python chafa curl
        ;;
    *)
        echo -e "${RED}Error: Unsupported package manager. Please install git, python3, and chafa manually.${NC}"
        exit 1
        ;;
esac

# 3. Installation Directory
echo -e "${YELLOW}[3/7] Setting up installation directory...${NC}"
DEFAULT_DIR="$HOME/riven-tui"
echo -n -e "Where should I install Riven TUI? [Default: $DEFAULT_DIR]: "
read INSTALL_DIR < /dev/tty
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_DIR}

# Handle existing directory
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}Directory $INSTALL_DIR already exists.${NC}"
    echo -n "Overwrite? (y/N): "
    read OVERWRITE < /dev/tty
    if [[ ! $OVERWRITE =~ ^[Yy]$ ]]; then
        echo -e "${RED}Setup aborted.${NC}"
        exit 1
    fi
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 4. Clone Repository
echo -e "${YELLOW}[4/7] Downloading Riven TUI...${NC}"
git clone https://github.com/subvhome/riven-tui.git .

# 5. Virtual Environment
echo -e "${YELLOW}[5/7] Setting up Python environment...${NC}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip > /dev/null
pip install -r requirements.txt > /dev/null

# 6. Configuration Wizard
echo -e "\n${BLUE}--- Configuration Wizard ---${NC}"
echo -n "Riven API Key: "
read RIVEN_API_KEY < /dev/tty
echo -n "TMDB Bearer Token: "
read TMDB_TOKEN < /dev/tty

echo -n "Backend Host [localhost]: "
read RIVEN_HOST < /dev/tty
RIVEN_HOST=${RIVEN_HOST:-localhost}
echo -n "Backend Port [8080]: "
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
sed -i '/^$/d' settings.json

# 7. Final Polish (The Launcher Fix)
echo -e "${YELLOW}[7/7] Finishing up...${NC}"

# Create the runner script with the directory-switch fix
cat > run.sh <<EOF
#!/bin/bash
export COLORTERM=truecolor
# Absolute path to the app directory
APP_DIR="$INSTALL_DIR"
cd "\$APP_DIR"
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi
exec python3 riven_tui.py "\$@"
EOF
chmod +x run.sh

# Alias setup
echo -e "\n${BLUE}==========================================${NC}"
echo -e "${GREEN}      Setup Complete!${NC}"
echo -e "${BLUE}==========================================${NC}"

echo -n "Add 'riven-tui' alias to your shell profile? [y/N]: "
read ADD_ALIAS < /dev/tty
if [[ $ADD_ALIAS =~ ^[Yy]$ ]]; then
    SHELL_PROFILE=""
    [[ "$SHELL" == *"zsh"* ]] && SHELL_PROFILE="$HOME/.zshrc"
    [[ "$SHELL" == *"bash"* ]] && SHELL_PROFILE="$HOME/.bashrc"
    [[ -z "$SHELL_PROFILE" ]] && SHELL_PROFILE="$HOME/.profile"

    if [ -n "$SHELL_PROFILE" ]; then
        if ! grep -q "alias riven-tui=" "$SHELL_PROFILE"; then
            echo "alias riven-tui='$INSTALL_DIR/run.sh'" >> "$SHELL_PROFILE"
            echo -e "${GREEN}✓ Alias added. Run 'source $SHELL_PROFILE' to enable it.${NC}"
        fi
    fi
fi

echo -e "\nStart the app anytime by typing: ${CYAN}riven-tui${NC}"
