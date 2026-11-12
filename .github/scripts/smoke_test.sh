#!/usr/bin/env bash
# Start the app from a fresh database and check it serves its key pages.
set -euo pipefail

python manage.py migrate --noinput
python manage.py runserver 127.0.0.1:8000 --noreload > server.log 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health/ > /dev/null; then break; fi
  sleep 1
done

check() {
  local path=$1 expected=$2
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$path")
  echo "GET $path -> $code (expected $expected)"
  [ "$code" = "$expected" ] || { cat server.log; exit 1; }
}

check /health/ 200
check /login/ 200
check /dashboard/ 302          # logged out: redirected to login
check /api/auth/me/ 401        # API needs a token
check /admin/login/ 200

echo "Smoke test passed."
