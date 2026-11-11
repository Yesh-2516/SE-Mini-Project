#!/usr/bin/env bash
# Run TC-Sec-01 (OEP-SR-001) against the real deploy/nginx.conf on this machine.
#
# Starts nginx in Docker with a throwaway self-signed certificate, runs Django
# behind it with DJANGO_TLS_ENABLED=1 on a throwaway database, then checks the
# redirect, HTTPS, HSTS and which TLS versions the server accepts. Nothing is
# installed and db.sqlite3 is not touched. See docs/tls_deployment.md.
#
# Needs: Docker, curl, and the project's virtual environment.
#   bash deploy/tls_check/check_tls.sh
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HTTP_PORT="${HTTP_PORT:-8080}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
DJANGO_PORT=8000  # Must match proxy_pass in deploy/nginx.conf.
NGINX_IMAGE="${NGINX_IMAGE:-nginx:1.27-alpine}"
OPENSSL_IMAGE="${OPENSSL_IMAGE:-alpine/openssl:latest}"
CONTAINER=oep-tls-check

if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  PYTHON="${PYTHON:-$ROOT/.venv/Scripts/python.exe}"
else
  PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
fi

# Git Bash on Windows rewrites anything that looks like a path, including
# paths inside containers. Turn that off and convert host paths ourselves.
if command -v cygpath >/dev/null 2>&1; then
  export MSYS_NO_PATHCONV=1
  host_path() { cygpath -m "$1"; }
else
  host_path() { echo "$1"; }
fi

WORK="$(mktemp -d)"
DJANGO_PID=""
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  [ -n "$DJANGO_PID" ] && kill "$DJANGO_PID" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT

PASSED=0
FAILED=0
result() {  # result PASS|FAIL "check" "detail"
  printf '| %s | %s | %s |\n' "$2" "$1" "$3"
  if [ "$1" = PASS ]; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); fi
}

# --- Certificate and nginx config ---------------------------------------------

mkdir -p "$WORK/certs" "$WORK/static"
docker run --rm -v "$(host_path "$WORK/certs"):/certs" "$OPENSSL_IMAGE" req -x509 -newkey rsa:2048 -nodes \
  -keyout /certs/privkey.pem -out /certs/fullchain.pem -days 1 -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost" >/dev/null 2>&1 || { echo "Could not create a certificate"; exit 1; }

# The real config, with only the domain, upstream address and static path
# swapped for this machine.
sed -e "s/exam-portal\.example\.edu/localhost/g" \
    -e "s#proxy_pass http://127.0.0.1:$DJANGO_PORT#proxy_pass http://host.docker.internal:$DJANGO_PORT#" \
    -e "s#/srv/exam-portal/staticfiles/#/srv/static/#" \
    "$ROOT/deploy/nginx.conf" > "$WORK/default.conf"

NGINX_ARGS=(
  -v "$(host_path "$WORK/default.conf"):/etc/nginx/conf.d/default.conf:ro"
  -v "$(host_path "$WORK/certs"):/etc/nginx/certs:ro"
  -v "$(host_path "$WORK/static"):/srv/static:ro"
  --add-host host.docker.internal:host-gateway
)
if ! docker run --rm "${NGINX_ARGS[@]}" "$NGINX_IMAGE" nginx -t >"$WORK/nginx-t.log" 2>&1; then
  cat "$WORK/nginx-t.log"
  echo "deploy/nginx.conf failed nginx -t"
  exit 1
fi
docker rm -f "$CONTAINER" >/dev/null 2>&1
docker run -d --name "$CONTAINER" -p "$HTTP_PORT:80" -p "$HTTPS_PORT:443" "${NGINX_ARGS[@]}" "$NGINX_IMAGE" >/dev/null \
  || { echo "Could not start nginx"; exit 1; }

# --- Django with TLS settings on ---------------------------------------------

export PYTHONPATH="$(host_path "$ROOT/docs/browser_checks")"
export DJANGO_SETTINGS_MODULE=check_settings
export BROWSER_CHECKS_DB="$(host_path "$WORK/tls.sqlite3")"
export DJANGO_TLS_ENABLED=1
export DJANGO_SECRET_KEY="tls-check-$(date +%s)-$RANDOM$RANDOM$RANDOM-not-for-production-use-0123456789"
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

cd "$ROOT"
"$PYTHON" manage.py migrate -v0 || { echo "migrate failed"; exit 1; }
DEPLOY_CHECK="$("$PYTHON" manage.py check --deploy 2>&1)"
DEPLOY_STATUS=$?
# Listen on all interfaces so the nginx container can reach it.
"$PYTHON" manage.py runserver "0.0.0.0:$DJANGO_PORT" --noreload >"$WORK/django.log" 2>&1 &
DJANGO_PID=$!
for _ in $(seq 1 30); do
  curl -s -o /dev/null "http://127.0.0.1:$DJANGO_PORT/" && break
  sleep 1
done

# --- Checks -------------------------------------------------------------------

echo
echo "| Check | Result | Detail |"
echo "|---|---|---|"

if [ $DEPLOY_STATUS -eq 0 ] && echo "$DEPLOY_CHECK" | grep -q "no issues"; then
  result PASS "\`manage.py check --deploy\` with TLS on" "$(echo "$DEPLOY_CHECK" | tail -1)"
else
  result FAIL "\`manage.py check --deploy\` with TLS on" "$(echo "$DEPLOY_CHECK" | tr '\n' ' ' | cut -c1-200)"
fi

redirect_of() {  # Prints the status code and Location header of one request.
  local headers
  headers="$(curl -s -D - -o /dev/null "$1" | tr -d '\r')"
  echo "$(echo "$headers" | head -1 | awk '{print $2}') $(echo "$headers" | grep -i '^location:' | awk '{print $2}')"
}

# nginx: plain HTTP is redirected.
read -r CODE LOCATION < <(redirect_of "http://localhost:$HTTP_PORT/api/auth/me/")
if [ "$CODE" = 301 ] && [[ "$LOCATION" == https://localhost/api/auth/me/ ]]; then
  result PASS "nginx redirects HTTP to HTTPS" "$CODE to $LOCATION"
else
  result FAIL "nginx redirects HTTP to HTTPS" "got $CODE to '$LOCATION'"
fi

# The site is served over HTTPS, through nginx to Django.
HEADERS="$(curl -sk -D - -o /dev/null "https://localhost:$HTTPS_PORT/api/auth/me/")"
CODE="$(echo "$HEADERS" | head -1 | awk '{print $2}')"
if [ "$CODE" = 401 ]; then
  result PASS "HTTPS is served by Django through nginx" "\`/api/auth/me/\` returned 401 over TLS"
else
  result FAIL "HTTPS is served by Django through nginx" "got $CODE"
fi
HSTS="$(echo "$HEADERS" | grep -i '^strict-transport-security' | tr -d '\r')"
if [ -n "$HSTS" ]; then
  result PASS "HSTS header sent over HTTPS" "$HSTS"
else
  result FAIL "HSTS header sent over HTTPS" "missing"
fi
CODE="$(curl -sk -o /dev/null -w '%{http_code}' "https://localhost:$HTTPS_PORT/login/")"
COOKIE="$(curl -sk -D - -o /dev/null "https://localhost:$HTTPS_PORT/login/" | grep -i '^set-cookie: csrftoken' | tr -d '\r')"
if [ "$CODE" = 200 ] && echo "$COOKIE" | grep -qi 'secure'; then
  result PASS "Website login page over HTTPS, cookie marked Secure" "200, \`${COOKIE%%=*}\` has Secure"
else
  result FAIL "Website login page over HTTPS, cookie marked Secure" "got $CODE, cookie '$COOKIE'"
fi

# Django on its own also redirects plain HTTP, in case the proxy is bypassed.
read -r CODE LOCATION < <(redirect_of "http://localhost:$DJANGO_PORT/api/auth/me/")
if [ "$CODE" = 301 ] && [[ "$LOCATION" == https://* ]]; then
  result PASS "Django redirects plain HTTP itself" "$CODE to $LOCATION"
else
  result FAIL "Django redirects plain HTTP itself" "got $CODE to '$LOCATION'"
fi

# TLS versions. The client runs in Docker with SECLEVEL=0 so it is willing to
# offer TLS 1.0 and 1.1: a failure then means the server refused them.
handshake() {  # handshake -tls1_2
  docker run --rm --add-host host.docker.internal:host-gateway --entrypoint sh "$OPENSSL_IMAGE" -c \
    "echo | openssl s_client -connect host.docker.internal:$HTTPS_PORT -servername localhost $1 -cipher 'DEFAULT@SECLEVEL=0' 2>&1"
}
for version in tls1_2 tls1_3; do
  OUT="$(handshake "-$version")"
  LABEL="TLS $(echo "${version#tls}" | tr _ .)"
  if echo "$OUT" | grep -q -- "-----BEGIN CERTIFICATE-----"; then
    result PASS "$LABEL accepted" "$(echo "$OUT" | grep -m1 'Cipher is' | sed 's/^ *//')"
  else
    result FAIL "$LABEL accepted" "$(echo "$OUT" | grep -m1 -i error)"
  fi
done

# Control: the same client really can speak TLS 1.1 when a server allows it,
# so the refusals below come from our server, not from the client.
CONTROL="$(docker run --rm --entrypoint sh "$OPENSSL_IMAGE" -c "
  openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/k.pem -out /tmp/c.pem -days 1 -subj /CN=control >/dev/null 2>&1
  openssl s_server -accept 4433 -cert /tmp/c.pem -key /tmp/k.pem -tls1_1 -cipher 'DEFAULT@SECLEVEL=0' -quiet >/dev/null 2>&1 &
  sleep 1
  echo | openssl s_client -connect 127.0.0.1:4433 -tls1_1 -cipher 'DEFAULT@SECLEVEL=0' 2>&1")"
if echo "$CONTROL" | grep -q -- "-----BEGIN CERTIFICATE-----"; then
  result PASS "Control: client can offer TLS 1.1" "handshake with a TLS 1.1-only test server succeeded"
else
  result FAIL "Control: client can offer TLS 1.1" "the client can't test old versions, so the refusals below prove nothing"
fi

for version in tls1_1 tls1; do
  OUT="$(handshake "-$version")"
  LABEL="TLS $(echo "${version#tls}" | tr _ . | sed 's/^1$/1.0/')"
  if echo "$OUT" | grep -q -- "-----BEGIN CERTIFICATE-----"; then
    result FAIL "$LABEL refused" "handshake succeeded"
  elif echo "$OUT" | grep -qi "alert protocol version"; then
    # The alert is sent by the server during the handshake.
    result PASS "$LABEL refused" "server answered: $(echo "$OUT" | grep -m1 -oi "[a-z0-9 ]*alert protocol version")"
  else
    result FAIL "$LABEL refused" "inconclusive: $(echo "$OUT" | grep -m1 -i error)"
  fi
done

echo
echo "Client: $(docker run --rm --entrypoint openssl "$OPENSSL_IMAGE" version), server: $(docker run --rm --entrypoint nginx "$NGINX_IMAGE" -v 2>&1 | sed 's/.*: //') ($NGINX_IMAGE)"
echo "$PASSED passed, $FAILED failed."
[ "$FAILED" -eq 0 ]
