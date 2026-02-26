#!/usr/bin/env bash
# Queryon — backend, frontend, Qdrant ve (opsiyonel) PostgreSQL durdur.
# Usage: ./stop.sh

set -e
cd "$(dirname "$0")"

echo "==> Stopping frontend..."
if [ -f .frontend.pid ]; then
  kill "$(cat .frontend.pid)" 2>/dev/null || true
  rm -f .frontend.pid
fi
pkill -f "next dev" 2>/dev/null || true

echo "==> Stopping backend..."
if [ -f .backend.pid ]; then
  kill "$(cat .backend.pid)" 2>/dev/null || true
  rm -f .backend.pid
fi
pkill -f "uvicorn backend.api.main" 2>/dev/null || true

echo "==> Stopping Qdrant (Docker)..."
docker stop qdrant 2>/dev/null || true

echo "==> PostgreSQL: brew services stop postgresql (isteğe bağlı)"
# Brew postgres'i de durdurmak için aşağıdaki satırı açın:
# brew services stop postgresql@14 2>/dev/null || brew services stop postgresql 2>/dev/null || true

echo "Done."
