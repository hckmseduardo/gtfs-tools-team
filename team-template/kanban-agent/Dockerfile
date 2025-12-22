FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Node.js for Claude CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    gnupg \
    openssh-client \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI (for Pro subscription users)
RUN npm install -g @anthropic-ai/claude-code

# Install uv for fast dependency management
RUN pip install uv

# Create volume mount points
VOLUME ["/app/target-project", "/root/.claude"]

# Create .ssh directory for SSH key mount
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Environment variables for git repo
ENV KANBAN_AGENTS_REPO=https://github.com/hckmseduardo/kanban-agents.git
ENV KANBAN_AGENTS_BRANCH=main
ENV AUTO_UPDATE=true

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose the webhook server port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
