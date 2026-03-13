#!/bin/bash

# Riven TUI - Release Automation Script
# Fetches latest version from GitHub, proposes increment, and handles tagging.

set -e

# --- Colors for Output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================="
echo -e "      🚀 Riven TUI Release Helper"
echo -e "==========================================${NC}"

# --- NEW: Pre-flight Sync Check ---
echo -e "${YELLOW}Checking sync status with GitHub...${NC}"
git fetch origin main

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})
BASE=$(git merge-base @ @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}✓ Local is up-to-date with remote.${NC}"
elif [ "$LOCAL" = "$BASE" ]; then
    echo -e "${RED}✗ Remote has changes you don't have. You should pull first.${NC}"
    echo -en "${BLUE}Action? [p]ull, [f]orce push anyway, [a]bort: ${NC}"
    read SYNC_CHOICE < /dev/tty
    case $SYNC_CHOICE in
        [Pp]* ) git pull origin main ;;
        [Ff]* ) echo -e "${YELLOW}Proceeding with force-push intent...${NC}"; FORCED=true ;;
        * ) exit 1 ;;
    esac
elif [ "$REMOTE" = "$BASE" ]; then
    echo -e "${YELLOW}Local is ahead of remote. Ready to push.${NC}"
else
    echo -e "${RED}✗ Branches have diverged! (Work exists on both sides)${NC}"
    echo -en "${BLUE}Action? [p]ull/merge, [f]orce push (OVERWRITE REMOTE), [a]bort: ${NC}"
    read SYNC_CHOICE < /dev/tty
    case $SYNC_CHOICE in
        [Pp]* ) git pull origin main ;;
        [Ff]* ) echo -e "${YELLOW}Warning: Remote changes will be lost.${NC}"; FORCED=true ;;
        * ) exit 1 ;;
    esac
fi
# ---------------------------------

# 1. Fetch latest version from GitHub tags
echo -e "${YELLOW}Fetching latest version from GitHub...${NC}"
LATEST_TAG=$(git ls-remote --tags origin | grep -o 'v[0-9.]*$' | sort -V | tail -n1 | sed 's/^v//')

if [ -z "$LATEST_TAG" ]; then
    echo -e "${YELLOW}No tags found on remote. Checking local version.py...${NC}"
    LATEST_TAG=$(grep "VERSION =" version.py | cut -d'"' -f2)
fi

echo -e "${GREEN}Current remote version: v$LATEST_TAG${NC}"

# 2. Calculate next version (increment patch)
IFS='.' read -r major minor patch <<< "$LATEST_TAG"
PROPOSED_VERSION="$major.$minor.$((patch + 1))"

# 3. Prompt user for version
echo -en "${BLUE}Enter new version [${PROPOSED_VERSION}]: ${NC}"
read INPUT_VERSION < /dev/tty
NEW_VERSION=${INPUT_VERSION:-$PROPOSED_VERSION}

# 4. Prompt for release message
echo -en "${BLUE}Enter release message: ${NC}"
read RELEASE_MSG < /dev/tty

if [ -z "$RELEASE_MSG" ]; then
    RELEASE_MSG="Release v$NEW_VERSION"
fi

# 5. Confirmation
echo -e "\n${YELLOW}Summary of release:${NC}"
echo -e "Version: ${GREEN}$NEW_VERSION${NC}"
echo -e "Message: ${GREEN}$RELEASE_MSG${NC}"
echo -en "\nProceed? (y/N): "
read CONFIRM < /dev/tty

if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo -e "${RED}Release aborted.${NC}"
    exit 1
fi

# 6. Update version.py
echo -e "${YELLOW}Updating version.py to $NEW_VERSION...${NC}"
echo "VERSION = \"$NEW_VERSION\"" > version.py

# 7. Git Operations
echo -e "${YELLOW}Staging and committing...${NC}"
git add .
git commit -m "chore: release v$NEW_VERSION - $RELEASE_MSG"

echo -e "${YELLOW}Tagging v$NEW_VERSION...${NC}"
git tag -a "v$NEW_VERSION" -m "$RELEASE_MSG"

echo -e "${YELLOW}Pushing to GitHub...${NC}"
if [ "$FORCED" = true ]; then
    git push origin main --force
else
    git push origin main
fi
git push origin --tags

echo -e "${GREEN}=========================================="
echo -e "      ✅ Successfully released v$NEW_VERSION!"
echo -e "==========================================${NC}"
