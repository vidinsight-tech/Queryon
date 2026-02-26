#!/usr/bin/env bash
# Queryon — start PostgreSQL (brew), Qdrant (Docker), backend, frontend.
# Usage: ./start.sh

set -e
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a

# LLM is optional at startup: backend uses env keys if set, else first active LLM from DB (via API), else no-op message
echo "==> Starting PostgreSQL (brew)..."
brew services start postgresql@16 2>/dev/null || \
brew services start postgresql@15 2>/dev/null || \
brew services start postgresql@14 2>/dev/null || \
brew services start postgresql 2>/dev/null || true

echo "==> Waiting for Postgres (port 5432)..."
for i in $(seq 1 30); do
  nc -z 127.0.0.1 5432 2>/dev/null && break
  sleep 1
done
if ! nc -z 127.0.0.1 5432 2>/dev/null; then
  echo "ERROR: PostgreSQL is not listening on localhost:5432."
  echo "Start it manually: brew services start postgresql@14   (or @15 / @16 depending on your install)"
  echo "Check: brew services list | grep postgres"
  exit 1
fi

echo "==> Starting Qdrant (Docker)..."
docker start qdrant 2>/dev/null || docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant

echo "==> Waiting for Qdrant..."
sleep 2

echo "==> Starting backend (uvicorn)..."
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost:5432/queryon}"
export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
# LLM: set OPENAI_API_KEY or GEMINI_API_KEY in env or .env
if [ -d .venv ]; then
  .venv/bin/pip install -q -r backend/requirements.txt
  echo "==> Seeding hairdresser chatbot rules (idempotent)..."
  .venv/bin/python -m backend.scripts.seed_hairdresser || echo "WARNING: seed_hairdresser failed (non-fatal)"
  .venv/bin/python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000 &
else
  echo "WARNING: .venv not found, using system python. Create one with: python3 -m venv .venv && pip install -r backend/requirements.txt"
  python3 -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000 &
fi
BACKEND_PID=$!
echo $BACKEND_PID > .backend.pid

echo "==> Waiting for backend to listen..."
for i in {1..30}; do
  curl -s -o /dev/null http://localhost:8000/health 2>/dev/null && break
  sleep 0.5
done

echo "==> Starting frontend (Next.js)..."
cd frontend
[ -f .env.local ] || echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev &
FRONTEND_PID=$!
cd ..
echo $FRONTEND_PID > .frontend.pid

echo ""
echo "Backend:  http://localhost:8000  (PID $BACKEND_PID)"
echo "Frontend: http://localhost:3000  (PID $FRONTEND_PID)"
echo "Stop with: ./stop.sh"
echo ""
wait $FRONTEND_PID 2>/dev/null || true
