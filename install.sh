#!/bin/bash

# Riven TUI - Interactive Installer
# This script automates the setup of Riven TUI for a smooth onboarding experience.

set -e

# --- Colors for Output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================="
echo -e "      🚀 Welcome to the Riven TUI Setup"
echo -e "==========================================${NC}"

# 1. Dependency Checks
echo -e "${YELLOW}[1/6] Checking system requirements...${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed. Please install git and try again.${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install Python 3.12+ and try again.${NC}"
    exit 1
fi

# Check Python version (requires 3.12+)
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)'; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    echo -e "${YELLOW}Warning: Riven TUI recommends Python 3.12+. Found version $PYTHON_VERSION.${NC}"
fi

# 2. Installation Directory
echo -e "${YELLOW}[2/6] Setting up installation directory...${NC}"
DEFAULT_DIR="$HOME/riven-tui"
echo -n "Where should I install Riven TUI? [Default: $DEFAULT_DIR]: "
read INSTALL_DIR < /dev/tty
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_DIR}

if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}Directory $INSTALL_DIR already exists.${NC}"
    echo -n "Should I overwrite it? (y/N): "
    read OVERWRITE < /dev/tty
    if [[ ! $OVERWRITE =~ ^[Yy]$ ]]; then
        echo -e "${RED}Setup aborted.${NC}"
        exit 1
    fi
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 3. Clone Repository
echo -e "${YELLOW}[3/6] Cloning Riven TUI from GitHub...${NC}"
git clone https://github.com/subvhome/riven-tui.git .

# 4. Virtual Environment & Dependencies
echo -e "${YELLOW}[4/6] Setting up Python environment (this may take a minute)...${NC}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip > /dev/null
pip install -r requirements.txt > /dev/null

# 5. Configuration Wizard

echo -e "\n${BLUE}--- Configuration Wizard ---${NC}"

echo -e "Let's set up your settings. Press Enter to use defaults.\n"




echo -n "Riven API Key: "

read RIVEN_API_KEY < /dev/tty

echo -n "TMDB Bearer Token: "

read TMDB_TOKEN < /dev/tty




echo -n "Backend Protocol [http]: "
read RIVEN_PROTO < /dev/tty
RIVEN_PROTO=${RIVEN_PROTO:-http}
echo -n "Backend Host [localhost]: "
read RIVEN_HOST < /dev/tty
RIVEN_HOST=${RIVEN_HOST:-localhost}
echo -n "Backend Port [8080]: "
read RIVEN_PORT < /dev/tty
RIVEN_PORT=${RIVEN_PORT:-8080}

echo -e "\n${BLUE}Advanced Settings${NC}"

echo -n "Request Timeout (seconds) [30.0]: "

read REQ_TIMEOUT < /dev/tty

REQ_TIMEOUT=${REQ_TIMEOUT:-30.0}

echo -n "Log Display Limit (lines) [50]: "

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



# Post-process to remove all blank lines from the generated JSON
sed -i '/^$/d' settings.json

echo -e "${GREEN}✓ settings.json created successfully.${NC}"





# 6. Optional Tools (Chafa)

if ! command -v chafa &> /dev/null; then




echo -e "\n${YELLOW}[5/6] Chafa (for poster art) not found.${NC}"




echo -n "Would you like to try installing chafa? (Requires sudo) [Y/n]: "




    read INSTALL_CHAFA < /dev/tty

    INSTALL_CHAFA=${INSTALL_CHAFA:-y}

    

    if [[ $INSTALL_CHAFA =~ ^[Yy]$ ]]; then



        if [[ "$OSTYPE" == "linux-gnu"* ]]; then



            if command -v apt-get &> /dev/null; then



                sudo apt-get update && sudo apt-get install -y chafa



            elif command -v dnf &> /dev/null; then



                sudo dnf install -y chafa



            elif command -v pacman &> /dev/null; then



                sudo pacman -S --noconfirm chafa



            fi



        elif [[ "$OSTYPE" == "darwin"* ]]; then



            if command -v brew &> /dev/null; then



                brew install chafa



            else



                echo -e "${RED}Homebrew not found. Please install chafa manually.${NC}"



            fi



        fi



    fi

else



    echo -e "${GREEN}✓ Chafa is already installed.${NC}"



fi





# 7. Final Polish (Alias/Launch Script) 

echo -e "${YELLOW}[6/6] Finishing up...${NC}"





# Create a local runner script

cat > run.sh <<EOF
#!/bin/bash
cd "$INSTALL_DIR"
source .venv/bin/activate
python3 riven_tui.py
EOF
chmod +x run.sh





# Offer to add an alias to shell profile


echo -e "\n${BLUE}==========================================${NC}"

echo -e "${GREEN}      Riven TUI is ready to go!${NC}"


echo -e "${BLUE}==========================================${NC}"

echo -e "You can start the app by running:"


echo -e "${YELLOW}cd $INSTALL_DIR && ./run.sh${NC}
"



echo -n "Would you like to add a 'riven-tui' alias to your shell profile? [y/N]: "




read ADD_ALIAS < /dev/tty

if [[ $ADD_ALIAS =~ ^[Yy]$ ]]; then




    SHELL_PROFILE=""

    if [[ "$SHELL" == *"zsh"* ]]; then



        SHELL_PROFILE="$HOME/.zshrc"



    elif [[ "$SHELL" == *"bash"* ]]; then



        SHELL_PROFILE="$HOME/.bashrc"



    fi




    if [ -n "$SHELL_PROFILE" ]; then



        echo "alias riven-tui='$INSTALL_DIR/run.sh'" >> "$SHELL_PROFILE"



        echo -e "${GREEN}✓ Alias added to $SHELL_PROFILE. Please restart your terminal or run 'source $SHELL_PROFILE'.${NC}"



    fi



fi



echo -e "\nEnjoy using Riven TUI!"
