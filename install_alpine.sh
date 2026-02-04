#!/bin/sh

# Riven TUI - Alpine Interactive Installer
# Tailored for Alpine Linux systems using apk and wget.
# This script is POSIX-compliant for compatibility with Alpine's default 'ash' shell.

set -e

# --- Colors for Output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

printf "${BLUE}==========================================\n"
printf "   🚀 Riven TUI Setup (Alpine Edition)\n"
printf "==========================================${NC}\n"

# 1. Dependency Checks & Installation
printf "${YELLOW}[1/6] Checking and installing system requirements...${NC}\n"

# Check for pending updates
printf "${BLUE}Checking for pending system updates...${NC}\n"
UPDATES=$(apk version -v | grep -c '<' || echo "0")
if [ "$UPDATES" -gt 0 ]; then
    printf "${YELLOW}⚠️  Notice: There are $UPDATES pending system updates.${NC}\n"
    printf "It is recommended to run ${BLUE}apk update && apk upgrade${NC} before installing new software.\n"
    printf "Would you like to continue anyway? (y/N): "
    read CONTINUE_INSTALL < /dev/tty
    case "$CONTINUE_INSTALL" in
        [Yy]*) ;; 
        *) printf "${RED}Setup aborted. Please update your system and try again.${NC}\n"; exit 1 ;; 
    esac
fi

# Ensure we have the basics
if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
else
    SUDO=""
fi

# Install core dependencies via apk
$SUDO apk update
$SUDO apk add git python3 py3-pip chafa wget coreutils sed

# Verify Python version (requires 3.12+)
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)'; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))
')
    printf "${YELLOW}Warning: Riven TUI recommends Python 3.12+. Found version $PYTHON_VERSION.${NC}\n"
fi

# 2. Installation Directory
printf "${YELLOW}[2/6] Setting up installation directory...${NC}\n"
DEFAULT_DIR="$HOME/riven-tui"
printf "Where should I install Riven TUI? [Default: $DEFAULT_DIR]: "
read INSTALL_DIR < /dev/tty
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_DIR}

if [ -d "$INSTALL_DIR" ]; then
    printf "${YELLOW}Directory $INSTALL_DIR already exists.${NC}\n"
    printf "Should I overwrite it? (y/N): "
    read OVERWRITE < /dev/tty
    case "$OVERWRITE" in
        [Yy]*) ;; 
        *) printf "${RED}Setup aborted.${NC}\n"; exit 1 ;; 
    esac
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 3. Clone Repository using wget (fetching tarball for Alpine minimal envs)
printf "${YELLOW}[3/6] Fetching Riven TUI via wget...${NC}\n"
wget -O riven-tui.tar.gz https://github.com/subvhome/riven-tui/archive/refs/heads/main.tar.gz
tar -xzf riven-tui.tar.gz --strip-components=1
rm riven-tui.tar.gz

# 4. Virtual Environment & Dependencies
printf "${YELLOW}[4/6] Setting up Python environment...${NC}\n"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Configuration Wizard
printf "\n${BLUE}--- Configuration Wizard ---${NC}\n"
printf "Let's set up your settings. Press Enter to use defaults.\n\n"

printf "Riven API Key: "
read RIVEN_API_KEY < /dev/tty

printf "TMDB Bearer Token: "
read TMDB_TOKEN < /dev/tty

printf "Backend Protocol [http]: "
read RIVEN_PROTO < /dev/tty
RIVEN_PROTO=${RIVEN_PROTO:-http}

printf "Backend Host [localhost]: "
read RIVEN_HOST < /dev/tty
RIVEN_HOST=${RIVEN_HOST:-localhost}

printf "Backend Port [8080]: "
read RIVEN_PORT < /dev/tty
RIVEN_PORT=${RIVEN_PORT:-8080}

printf "\n${BLUE}Advanced Settings${NC}\n"
printf "Request Timeout (seconds) [30.0]: "
read REQ_TIMEOUT < /dev/tty
REQ_TIMEOUT=${REQ_TIMEOUT:-30.0}

printf "Log Display Limit (lines) [50]: "
read LOG_LIMIT < /dev/tty
LOG_LIMIT=${LOG_LIMIT:-50}

# Create settings.json
cat > settings.json <<EOF
{
    "riven_key": "$RIVEN_API_KEY",
    "tmdb_bearer_token": "$TMDB_TOKEN",
    "be_config": {
        "protocol": "$RIVEN_PROTO",
        "host": "$RIVEN_HOST",
        "port": $RIVEN_PORT
    },
    "request_timeout": $REQ_TIMEOUT,
    "log_display_limit": $LOG_LIMIT,
    "log_tailing_enabled": true,
    "chafa_max_width": 100
}
EOF

# Post-process to remove all blank lines
sed -i '/^$/d' settings.json
printf "${GREEN}✓ settings.json created successfully.${NC}\n"

# 6. Final Polish
printf "${YELLOW}[6/6] Finishing up...${NC}\n"

cat > run.sh <<EOF
#!/bin/sh
export COLORTERM=truecolor
cd "$INSTALL_DIR"
. .venv/bin/activate
python3 riven_tui.py
EOF
chmod +x run.sh

printf "\n${BLUE}==========================================${NC}\n"
printf "${GREEN}      Riven TUI is ready to go!${NC}\n"
printf "==========================================${NC}\n"
printf "You can start the app by running:\n"
printf "${YELLOW}cd $INSTALL_DIR && ./run.sh${NC}\n\n"

printf "Would you like to add a 'riven-tui' alias to your shell profile? [y/N]: "
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
            printf "alias riven-tui='$INSTALL_DIR/run.sh'\n" >> "$SHELL_PROFILE"
            printf "${GREEN}✓ Alias added to $SHELL_PROFILE. Please restart your terminal or run '. $SHELL_PROFILE'.${NC}\n"
        fi
        ;; 
esac

printf "\nEnjoy using Riven TUI on Alpine!\n"