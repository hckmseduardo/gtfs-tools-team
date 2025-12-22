#!/bin/bash
set -e

REPO_DIR="/app/kanban-agents"

echo "=== Kanban Agents Startup ==="
echo "Repository: ${KANBAN_AGENTS_REPO}"
echo "Branch: ${KANBAN_AGENTS_BRANCH}"
echo "Auto-update: ${AUTO_UPDATE}"

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

# Install/update dependencies
echo "Installing dependencies..."
cd "$REPO_DIR"
uv pip install --system -e . --quiet

# Add repo to Python path
export PYTHONPATH="$REPO_DIR:$PYTHONPATH"

echo "Starting Kanban Agents server..."
cd "$REPO_DIR"
exec python -m src.main
