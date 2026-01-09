#!/bin/bash

# Riven TUI - Release Automation Script
# Usage: ./release.sh <version> "your message here"

if [ -z "$1" ]; then
    echo "Usage: ./release.sh <version_number> [message]"
    exit 1
fi

NEW_VERSION=$1
# Use second argument as message, or default if empty
RELEASE_MSG=${2:-"Release v$NEW_VERSION"}

# 1. Update version.py
echo "Updating version.py to $NEW_VERSION..."
echo "VERSION = \"$NEW_VERSION\"" > version.py

# 2. Git Operations
echo "Staging changes..."
git add .

echo "Committing..."
git commit -m "chore: release v$NEW_VERSION - $RELEASE_MSG"

echo "Tagging..."
git tag -a "v$NEW_VERSION" -m "$RELEASE_MSG"

echo "Pushing to GitHub..."
git push origin main
git push origin --tags

echo "------------------------------------------"
echo "🚀 Successfully released v$NEW_VERSION!"
echo "------------------------------------------"
