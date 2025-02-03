#!/bin/bash

# Ensure script exits if any command fails
set -e

# Set the repository URL securely (configure Git remote before running this)
REPO_URL="git@github.com:Pascal-Owilly/auto-video-upload.git"
# Add all changes
git add .

# One-time commit message
commit_message="update"
git commit -m "$commit_message"

# Push changes
git push "$REPO_URL" main

echo "✅ Changes pushed successfully!"
