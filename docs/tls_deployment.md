# TLS Deployment Guide (OEP-SR-001, TC-Sec-01)

Every client-server connection must use TLS 1.2 or higher. TLS is handled in two places:

- **nginx** (`deploy/nginx.conf`) holds the certificate, refuses TLS below 1.2 and redirects port 80 to HTTPS.
- **Django** (`DJANGO_TLS_ENABLED=1`) redirects any plain HTTP request that reaches it, sends HSTS and marks cookies as secure.

Local development is unchanged: without the variable, the app runs over plain HTTP.

## Deploying

1. Get a certificate for the server's domain and install it at the paths in `deploy/nginx.conf`.
2. Replace `exam-portal.example.edu` in `deploy/nginx.conf` with the real domain, and install the file in nginx.
3. Start Django behind nginx on `127.0.0.1:8000`, with these environment variables:

| Variable | Value | Purpose |
|---|---|---|
| `DJANGO_TLS_ENABLED` | `1` | Turns on the HTTPS settings |
| `DJANGO_ALLOWED_HOSTS` | `exam-portal.example.edu` | Comma-separated list of allowed domains |

Django must only be reachable through nginx. With `DJANGO_TLS_ENABLED=1` it trusts the `X-Forwarded-Proto` header, which a client could fake if it reached Django directly.

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
