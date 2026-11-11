# TLS Deployment Guide (OEP-SR-001, TC-Sec-01)

Every client-server connection must use TLS 1.2 or higher. TLS is handled in two places:

- **nginx** (`deploy/nginx.conf`) holds the certificate, refuses TLS below 1.2 and redirects port 80 to HTTPS.
- **Django** (`DJANGO_TLS_ENABLED=1`) redirects any plain HTTP request that reaches it, sends HSTS and marks cookies as secure.

Local development is unchanged: without the variable, the app runs over plain HTTP.

> **TLS is opt-in.** If `DJANGO_TLS_ENABLED` is forgotten on a server, Django serves plain HTTP with no warning, and the debug defaults stay on. Always run the `check --deploy` step below before going live.

## Deploying

1. Get a certificate for the server's domain and install it at the paths in `deploy/nginx.conf`.
2. Replace `exam-portal.example.edu` in `deploy/nginx.conf` with the real domain, and install the file in nginx.
3. Start Django behind nginx on `127.0.0.1:8000`, with these environment variables:

| Variable | Value | Purpose |
|---|---|---|
| `DJANGO_TLS_ENABLED` | `1` | Turns on the HTTPS settings |
| `DJANGO_ALLOWED_HOSTS` | `exam-portal.example.edu` | Comma-separated list of allowed domains |
| `DJANGO_SECRET_KEY` | A long random string | Signs sessions and tokens. Startup fails without it when TLS is on |
| `DJANGO_DEBUG` | Leave unset | Debug is off by default when TLS is on. Never set it to `1` on a server |

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

4. Gather the static files into `STATIC_ROOT`, then point the `/static/` location in `deploy/nginx.conf` at that folder:

```bash
python manage.py collectstatic --noinput
```

5. With the same environment variables set, run Django's deployment check. It must report no issues:

```bash
python manage.py check --deploy
```

The HSTS subdomain and preload warnings (`security.W005`, `security.W021`) are silenced on purpose. Both would apply HTTPS-only rules to every site on the institution's domain, so they should only be turned on with that domain's administrators.

Django must only be reachable through nginx. With `DJANGO_TLS_ENABLED=1` it trusts the `X-Forwarded-Proto` and `X-Forwarded-For` headers, which a client could fake if it reached Django directly. Audit logs record the last address in `X-Forwarded-For`, which is the one nginx added.

## Verifying (TC-Sec-01)

Run these against the deployed server:

| Check | Command | Expected |
|---|---|---|
| HTTP redirects to HTTPS | `curl -I http://<domain>/api/auth/me/` | `301` with an `https://` `Location` |
| HTTPS is served | `curl -I https://<domain>/api/auth/me/` | `401` from Django, over TLS |
| TLS 1.2 works | `openssl s_client -connect <domain>:443 -tls1_2` | Handshake succeeds |
| TLS 1.1 is refused | `openssl s_client -connect <domain>:443 -tls1_1` | Handshake fails |
| TLS 1.0 is refused | `openssl s_client -connect <domain>:443 -tls1` | Handshake fails |

Some OpenSSL builds have TLS 1.0 and 1.1 turned off, so the last two can fail on the client side alone. If the output says `no protocols available`, use a client that still supports them, such as `openssl s_client -cipher 'DEFAULT@SECLEVEL=0'` or `nmap --script ssl-enum-ciphers -p 443 <domain>`.

## Checking the configuration before deploying

`deploy/tls_check/check_tls.sh` runs TC-Sec-01 on a developer machine against the real `deploy/nginx.conf`, so a mistake in the config shows up before it reaches a server. It needs Docker, curl and the project's virtual environment:

```bash
bash deploy/tls_check/check_tls.sh
```

The script:

1. Creates a throwaway self-signed certificate for `localhost`.
2. Copies `deploy/nginx.conf`, changing only the domain, the upstream address and the static path, and checks it with `nginx -t`.
3. Starts nginx in Docker on ports 8080 (HTTP) and 8443 (HTTPS). Set `HTTP_PORT` and `HTTPS_PORT` to use others.
4. Runs Django on port 8000 with `DJANGO_TLS_ENABLED=1` and a throwaway database. `db.sqlite3` is not touched.
5. Runs the checks below, then removes the container and the temporary files.

The TLS client runs in Docker with `SECLEVEL=0`, so it is willing to offer TLS 1.0 and 1.1. A control check first confirms that it can complete a TLS 1.1 handshake with a test server that allows it. A version only counts as refused when our server sends `alert protocol version`, which can't come from the client.

This is not a substitute for checking the deployed server: the real certificate, domain and firewall can only be tested there, with the commands in the previous section.

### Last run

Run on 11 November 2026 at commit `dc9c698` (`main`), on Windows 11 with Docker Desktop.

| Check | Result | Detail |
|---|---|---|
| `manage.py check --deploy` with TLS on | PASS | System check identified no issues (2 silenced). |
| nginx redirects HTTP to HTTPS | PASS | 301 to https://localhost/api/auth/me/ |
| HTTPS is served by Django through nginx | PASS | `/api/auth/me/` returned 401 over TLS |
| HSTS header sent over HTTPS | PASS | Strict-Transport-Security: max-age=31536000 |
| Website login page over HTTPS, cookie marked Secure | PASS | 200, `Set-Cookie: csrftoken` has Secure |
| Django redirects plain HTTP itself | PASS | 301 to https://localhost:8000/api/auth/me/ |
| TLS 1.2 accepted | PASS | New, TLSv1.2, Cipher is ECDHE-RSA-AES256-GCM-SHA384 |
| TLS 1.3 accepted | PASS | New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384 |
| Control: client can offer TLS 1.1 | PASS | handshake with a TLS 1.1-only test server succeeded |
| TLS 1.1 refused | PASS | server answered: tlsv1 alert protocol version |
| TLS 1.0 refused | PASS | server answered: tlsv1 alert protocol version |

TLS client: OpenSSL 3.5.9 29 Sep 2026 (Library: OpenSSL 3.5.9 29 Sep 2026), server: nginx/1.27.5 (nginx:1.27-alpine).

