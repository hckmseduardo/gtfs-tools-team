#!/bin/bash
set -e

REPO_DIR="/app/kanban-agents"
TARGET_DIR="/app/target-project"

echo "=== Kanban Agents Startup ==="
echo "Repository: ${KANBAN_AGENTS_REPO}"
echo "Branch: ${KANBAN_AGENTS_BRANCH}"
echo "Auto-update: ${AUTO_UPDATE}"
echo "Sandbox Mode: ${SANDBOX_MODE:-false}"
echo "Sandbox Branch: ${SANDBOX_BRANCH:-}"

# Configure git credentials if GITHUB_TOKEN is provided
if [ -n "${GITHUB_TOKEN}" ]; then
    echo "Configuring GitHub token authentication..."
    git config --global credential.helper store
    echo "https://oauth2:${GITHUB_TOKEN}@github.com" > ~/.git-credentials
fi

# Configure SSH for GitHub if using SSH URL
if [[ "${KANBAN_AGENTS_REPO}" == git@* ]]; then
    echo "Configuring SSH for GitHub..."
    ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null || true
fi

# Clone or update the repository
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Cloning kanban-agents repository..."
    if git clone --branch "${KANBAN_AGENTS_BRANCH}" --single-branch "${KANBAN_AGENTS_REPO}" "$REPO_DIR"; then
        echo "Repository cloned successfully"
    else
        echo "ERROR: Failed to clone repository. Check your GITHUB_TOKEN or repository access."
        echo "For private repos, set GITHUB_TOKEN environment variable."
        exit 1
    fi
elif [ "$AUTO_UPDATE" = "true" ]; then
    echo "Pulling latest changes..."
    cd "$REPO_DIR"
    git fetch origin
    git reset --hard "origin/${KANBAN_AGENTS_BRANCH}"
    echo "Updated to latest commit: $(git rev-parse --short HEAD)"
    cd /app
fi

# In sandbox mode, configure git in target project for the sandbox branch
if [ "${SANDBOX_MODE}" = "true" ] && [ -d "$TARGET_DIR/.git" ]; then
    echo "=== Sandbox Mode Configuration ==="
    echo "Target project: $TARGET_DIR"
    cd "$TARGET_DIR"

    # Configure git user for commits
    git config user.name "Kanban Agent"
    git config user.email "kanban-agent@gtfs-tools.com"

    # Show current branch and status
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    echo "Current branch: $CURRENT_BRANCH"
    echo "Expected branch: ${SANDBOX_BRANCH}"

    # Ensure we're on the correct branch
    if [ -n "${SANDBOX_BRANCH}" ] && [ "$CURRENT_BRANCH" != "${SANDBOX_BRANCH}" ]; then
        echo "Switching to sandbox branch: ${SANDBOX_BRANCH}"
        git checkout "${SANDBOX_BRANCH}" 2>/dev/null || git checkout -b "${SANDBOX_BRANCH}" 2>/dev/null || true
    fi

    echo "Sandbox target project configured"
    cd /app
fi

# Install/update dependencies
echo "Installing dependencies..."
cd "$REPO_DIR"
uv pip install --system -e . --quiet

# Add repo to Python path
export PYTHONPATH="$REPO_DIR:$PYTHONPATH"

echo "Starting Kanban Agents server..."
cd "$REPO_DIR"
exec python -m src.main
