#!/bin/bash

# Riven TUI - Release Automation Script
# Usage: ./release.sh 1.2.0

if [ -z "$1" ]; then
    echo "Usage: ./release.sh <version_number> (e.g., 1.2.0)"
    exit 1
fi

NEW_VERSION=$1

# 1. Update version.py
echo "Updating version.py to $NEW_VERSION..."
echo "VERSION = \"$NEW_VERSION\"" > version.py

# 2. Git Operations
echo "Staging changes..."
git add .

echo "Committing..."
git commit -m "chore: release v$NEW_VERSION"

echo "Tagging..."
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"

echo "Pushing to GitHub..."
git push origin main
git push origin --tags

echo "------------------------------------------"
echo "🚀 Successfully released v$NEW_VERSION!"
echo "------------------------------------------"
