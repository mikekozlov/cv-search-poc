#!/usr/bin/env bash
# Deploy CV Search API to an Azure VM (Ubuntu 22.04+)
# Usage: scp this script + project to VM, then run it.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/cvsearch}"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"

echo "==> Installing Docker if not present..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable --now docker
    sudo usermod -aG docker "$USER"
    echo "Docker installed. You may need to re-login for group membership."
fi

echo "==> Ensuring Docker Compose plugin is available..."
if ! docker compose version &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y -qq docker-compose-plugin
fi

echo "==> Creating application directory..."
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

echo "==> Copying project files..."
# Assumes script is run from repo root
cp docker-compose.yml Dockerfile .dockerignore pyproject.toml README.md "$APP_DIR/"
cp BUILD_COMMIT "$APP_DIR/" 2>/dev/null || true
cp -r src "$APP_DIR/"
mkdir -p "$APP_DIR/data/lexicons"
cp -r data/lexicons/* "$APP_DIR/data/lexicons/" 2>/dev/null || true
cp api_server.py "$APP_DIR/" 2>/dev/null || true

if [ -f .env.production ]; then
    cp .env.production "$APP_DIR/.env"
    echo "   Copied .env.production -> .env"
else
    echo "   WARNING: No .env.production found. Create $APP_DIR/.env before starting."
fi

echo "==> Creating log and run directories..."
mkdir -p "$APP_DIR/logs" "$APP_DIR/runs"

cd "$APP_DIR"

echo "==> Building and starting services..."
BUILD_COMMIT=$(cat BUILD_COMMIT 2>/dev/null || echo "dev")
echo "   Build commit: $BUILD_COMMIT"
docker compose build --no-cache --build-arg BUILD_COMMIT="$BUILD_COMMIT"
docker compose up -d

echo "==> Waiting for Postgres to be healthy..."
for i in $(seq 1 30); do
    if docker compose exec postgres pg_isready -U cvsearch -d cvsearch &>/dev/null; then
        echo "   Postgres is ready."
        break
    fi
    sleep 2
done

echo "==> Initializing database schema..."
docker compose exec api python -c "
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
settings = Settings()
db = CVDatabase(settings)
db.initialize_schema()
db.close()
print('Schema initialized.')
"

echo "==> Verifying health endpoint..."
for i in $(seq 1 10); do
    if curl -sf http://localhost:8000/health &>/dev/null; then
        echo "   API is healthy!"
        echo ""
        echo "==> Deployment complete. API available at http://$(hostname -I | awk '{print $1}'):8000"
        echo "    Docs: http://$(hostname -I | awk '{print $1}'):8000/docs"
        exit 0
    fi
    sleep 2
done

echo "   WARNING: Health check did not pass. Check logs with: docker compose logs api"
exit 1
