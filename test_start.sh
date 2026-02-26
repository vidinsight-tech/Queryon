#!/usr/bin/env bash
# Queryon — aynı işler, test ortamı (test DB + aynı servisler).
# Usage: ./test_start.sh

set -e
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a

echo "==> Starting PostgreSQL (brew)..."
brew services start postgresql@14 2>/dev/null || brew services start postgresql 2>/dev/null || true

echo "==> Starting Qdrant (Docker)..."
docker start qdrant 2>/dev/null || docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant

echo "==> Waiting for Postgres..."
sleep 2

echo "==> Starting backend (test env)..."
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost:5432/queryon_test}"
export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
if [ -d .venv ]; then
  .venv/bin/pip install -q -r backend/requirements.txt
  .venv/bin/python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000 &
else
  python3 -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000 &
fi
BACKEND_PID=$!
echo $BACKEND_PID > .backend.pid

echo "==> Waiting for backend..."
for i in {1..30}; do
  curl -s -o /dev/null http://localhost:8000/health 2>/dev/null && break
  sleep 0.5
done

echo "==> Starting frontend (test)..."
cd frontend
[ -f .env.local ] || echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev &
FRONTEND_PID=$!
cd ..
echo $FRONTEND_PID > .frontend.pid

echo ""
echo "Test backend:  http://localhost:8000  (PID $BACKEND_PID)"
echo "Test frontend: http://localhost:3000  (PID $FRONTEND_PID)"
echo "Stop with: ./stop.sh"
echo ""
wait $FRONTEND_PID 2>/dev/null || true
