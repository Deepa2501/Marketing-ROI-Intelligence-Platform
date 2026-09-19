# Security Notes

Security review performed as part of Phase 15 (Platform Quality &
Portfolio Readiness). This is a portfolio/demonstration project; the
notes below record what was actually checked and what was found.

## Scope

All backend application code under `backend/` (services, routes,
config, app factory) and the frontend JavaScript under
`frontend/static/js/`. Test files are excluded from the "no dangerous
call" greps, since the security tests deliberately contain malicious
*strings* as fixtures (they are never executed).

## Checks performed and results

| Check | Method | Result |
|---|---|---|
| No `eval` / `exec` / `compile` on user input | grep across `backend/**/*.py` | **PASS** — the only matches are `re.compile()` calls on hard-coded regex literals in `copilot_service.py`. No dynamic evaluation of user input anywhere. |
| No `__import__` from user input | grep | **PASS** — no matches. |
| No shell execution | grep for `os.system`, `subprocess` | **PASS** — no matches in application code. (`python/generate_test_summary.py` uses `subprocess` to invoke pytest, but it takes no user input and is a developer tool, not a served endpoint.) |
| No raw SQL | grep for `SELECT/INSERT/DROP/execute(` | **PASS** — no matches. The platform has no SQL layer at all; all data access is pandas DataFrame operations. |
| No SQL built from user input | code review of Copilot, Campaign filters | **PASS** — campaign lookup uses a parameterized pandas equality comparison (`df[df["Campaign_ID"].astype(str).str.upper() == campaign_id.upper()]`), never a constructed query string. |
| No hard-coded secrets / API keys / passwords | grep for `api_key`, `password`, `token =` | **PASS** — no matches. |
| No arbitrary file writes from request handlers | grep for `open(..., 'w'/'a')` in `backend/` | **PASS** — no matches. The application is read-only with respect to the filesystem at request time. |
| No path traversal in user-facing endpoints | code review | **PASS** — no endpoint accepts a filesystem path from the user. All paths come from application config. |
| No absolute paths / secrets leaked in API responses | automated test | **PASS** — `test_platform_health.py` asserts the health response contains none of `/home/`, `/root/`, `C:\`, `password`, `secret_key=`, `api_key`, `token=`, and never echoes the actual `SECRET_KEY` value. |
| No stack traces exposed | automated tests across all phases | **PASS** — every route returns controlled JSON errors (`400` / `503` / `500`); tests assert `"Traceback"` never appears in responses. |
| Copilot input safety | 10 parameterized injection payloads | **PASS** — Python import/eval/exec, SQL `DROP`/`DELETE`, Jinja `{{7*7}}`, JNDI, pandas `to_csv`, shell `$(whoami)`, and path traversal are all handled as inert text. Verified `{{7*7}}` does not evaluate to 49 and that no filesystem side effects are created. |
| Frontend XSS | code review | **PASS** — `copilot.js` and `platform-health.js` escape all API- and user-supplied text before DOM insertion. Answers are treated as plain analytical text, never trusted HTML. |
| No external network calls at request time | code review | **PASS** — no outbound HTTP from any service. The Copilot is entirely rule-based and requires no AI API key. Chart.js is vendored locally (`frontend/static/js/vendor/chart.umd.js`), not pulled from a CDN. |

## Known items to address before any real deployment

These are **not** defects for a portfolio project, but must be handled
if this were ever deployed beyond a local demo:

1. **`SECRET_KEY` is the development default.** `backend/config.py`
   falls back to `"dev-secret-key-change-in-production"` when the
   environment variable is unset. The platform health endpoint
   deliberately raises this as a `WARN` rather than hiding it. Set a
   unique `SECRET_KEY` via environment variable before any shared
   deployment.
2. **No authentication or authorization.** Every page and API is
   publicly reachable. This is intentional for a local demo; a real
   deployment would need access control.
3. **No rate limiting.** Endpoints that run heavier computation
   (budget optimizer, data quality, forecasting) are unthrottled.
4. **Debug mode.** `FLASK_ENV=development` enables Flask debug mode.
   Use `FLASK_ENV=production` (and a WSGI server such as gunicorn) for
   anything non-local.

## Secrets handling

No secrets are committed to the repository. `.env.example` documents
the expected variables with placeholder values only; the real `.env`
is gitignored and never read into any API response. The platform
health check reports `SECRET_KEY` only as set / not-set / is-default —
it never echoes the value.
