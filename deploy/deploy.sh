#!/usr/bin/env bash
# Deploy xivLab to the configured server.
#
# Usage:
#   DEPLOY_HOST=user@sacurajima.example.com ./deploy/deploy.sh
#
# Steps:
#   1. rsync source tree to /opt/xivlab (excluding venv, data, build artifacts)
#   2. ssh + run `uv sync` to install pinned deps
#   3. ssh + run `alembic upgrade head` to apply migrations
#   4. ssh + restart the systemd service
#   5. local check_health.py against the public URL

set -euo pipefail

: "${DEPLOY_HOST:?DEPLOY_HOST=user@host required}"
: "${DEPLOY_PATH:=/opt/xivlab}"
: "${HEALTH_URL:=}"  # e.g. https://xivlab.example.com

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

echo "==> rsync to ${DEPLOY_HOST}:${DEPLOY_PATH}"
rsync -avz --delete \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='.ruff_cache/' \
    --exclude='data/' \
    --exclude='.git/' \
    --exclude='node_modules/' \
    --exclude='*.pyc' \
    ./ "${DEPLOY_HOST}:${DEPLOY_PATH}/"

echo "==> uv sync (server)"
ssh "${DEPLOY_HOST}" "cd ${DEPLOY_PATH} && uv sync --frozen"

echo "==> alembic upgrade head"
ssh "${DEPLOY_HOST}" "cd ${DEPLOY_PATH} && uv run alembic upgrade head"

echo "==> systemctl restart xivlab"
ssh "${DEPLOY_HOST}" "sudo systemctl restart xivlab"

if [[ -n "$HEALTH_URL" ]]; then
    echo "==> health check ${HEALTH_URL}"
    uv run python scripts/check_health.py "$HEALTH_URL"
fi

echo "==> deploy complete"
