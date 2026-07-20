# Monitoring

Wren's P0 observability: what is measured, what alerts, and how long data is kept.
There is **no Grafana at P0** (Prometheus retains the data regardless); the only
alert sink is Discord. Metric names and labels follow a stable convention so
rules and dashboards can be dropped in later.

Canonical sources:

- Instrumentation: `backend/src/wren/core/metrics.py` (HTTP), `backend/src/wren/core/observability.py` (domain/service/pool families), `backend/src/wren/core/db.py` (pool events), `mcp/src/wren_mcp/metrics.py` + `mcp/src/wren_mcp/tool_metrics.py` (MCP).
- Scrape + alert rules: `deployments/prometheus/prometheus.yml`, `deployments/prometheus/alerts.yml`.
- Alert routing: `deployments/alertmanager/alertmanager.yml`.
- Container topology, retention flags, and network placement: `docker-compose.yml`.

## Metrics

Both the backend and MCP expose `GET /metrics`. Each app concatenates its private
HTTP registry with its own custom-metrics registry: the backend serves the
domain/service/pool families (`WREN_REGISTRY`); the MCP server serves only the
tool-invocation counter (`TOOL_METRICS_REGISTRY`). These are two separate images
with disjoint registries, not one shared registry: the **App** column below says
which image emits each family. `/metrics` stays private via the Cloudflare ingress
path allow-list (which refuses it at the edge), not network isolation.

| Metric | App | Type | Labels | Emitted by |
|--------|-----|------|--------|-----------|
| `http_requests_total` | backend + mcp | counter | `method`, `path`, `status` | Every HTTP request (`path` = matched route template, e.g. `/roadmaps/{id}`, to bound cardinality) |
| `http_request_duration_seconds` | backend + mcp | histogram | `method`, `path` | Every HTTP request |
| `service_method_failures_total` | backend | counter | `service`, `method` | A public service method exiting with an **unexpected** error (see below) |
| `oauth_tokens_issued_total` | backend | counter | `grant_type` | OAuth token issuance by the AS (`authorization_code` = first issuance, `refresh_token` = rotation) |
| `mcp_tool_invocations_total` | mcp | counter | `tool`, `outcome` | Every MCP tool call (`outcome` = `ok`/`error`) |
| `db_query_duration_seconds` | backend | histogram | `query_name` | Every SQL statement (via SQLAlchemy engine events) |
| `active_connections` | backend | gauge | none | Connections checked out of the SQLAlchemy pool |

### Service-method failures: what counts

`service_method_failures_total` counts only faults that would surface as **5xx**.
Classification is by HTTP status over the `ExpectedError` base (which covers both
`WrenError` and the OAuth `OAuthError`): an `ExpectedError` with `status < 500` is
an expected result, not a failure, and is deliberately **not** counted, while one
with `status >= 500` (e.g. OAuth `server_error`) and any other exception is. So
the model-recoverable 4xx domain outcomes (`NotFound`, `Conflict`, `Validation`,
`Unauthorized`) and OAuth 4xx (`invalid_grant`/`invalid_client`) are excluded,
which keeps this metric correlated with the `HighErrorRate` alert instead of
being diluted by normal 404s/409s. Instrumentation is a
cross-cutting class decorator (`track_failures`); each public service method is
counted once (private helpers are not wrapped, and the service layer has no
public-to-public calls, so there is no double-counting). Thin delegating methods
add no timer of their own.

**Asymmetry with the MCP counter.** `mcp_tool_invocations_total{outcome}` counts a
model-recoverable 4xx (a backend error surfaced to the agent as a `ToolError`) as
`outcome="error"`, whereas the backend `service_method_failures_total`
deliberately **excludes** `WrenError` 4xx. This is intentional: the MCP counter
reports per-tool call outcomes (an agent's request failed), while the backend
counter reports operational faults (5xx-class). Do not compare their error counts
directly on a dashboard.

### DB `query_name`

To keep label cardinality bounded, `query_name` collapses to the SQL verb
(`select`/`insert`/`update`/`delete`, else `other`). A repository may override it
for a specific statement via SQLAlchemy `execution_options(query_name=...)`.

## Alerts

Prometheus evaluates three critical rules (`deployments/prometheus/alerts.yml`)
and routes them through Alertmanager to a single Discord webhook with
`send_resolved: true`, so both firing and recovery are posted.

| Alert | Condition | For |
|-------|-----------|-----|
| `ServiceDown` | `up == 0` (any scrape target) | 1m |
| `HostDiskAlmostFull` | filesystem available < 10% (non-tmpfs/overlay) | 2m |
| `HighErrorRate` | 5xx ratio of `http_requests_total` > 5% over 5m | 5m |

`node-exporter` provides the host filesystem series `HostDiskAlmostFull` reads
(memory series are exposed but unused at P0).

### Discord webhook templating (required for Alertmanager to start)

`deployments/alertmanager/alertmanager.yml` keeps a `${DISCORD_WEBHOOK_URL}`
placeholder in the committed file. Alertmanager does not expand environment
variables, so CI renders it (`envsubst` substitutes **only** that token) into the
`WREN_ALERTMANAGER_CONFIG` env var, which the `alertmanager` service receives as
an environment-sourced Compose secret (`0400`) at
`/etc/alertmanager/alertmanager.yml`; the Go templating (`{{ ... }}`) in the
title/message is left untouched and renders at alert time. `DISCORD_WEBHOOK_URL`
is a GitHub Actions secret (see `runbooks/deploy.md`). No rendered file is written to the
box; never commit a real webhook.

**This render is release-gating, not merely "needed for live firing."**
Alertmanager v0.27 **exits on config load** if `webhook_url` is not a valid URL
(an unrendered/blank placeholder → `unsupported scheme ""`). Because the deploy
health gate polls *every* service's healthcheck, a deploy that starts
Alertmanager without a rendered webhook will fail the gate and roll back. To avoid
crash-looping local dev, the `alertmanager` service is gated behind the `tunnels`
compose profile (the only profile the deploy activates), so `just up`/`up-dev` do
not start it; Prometheus and node-exporter still run locally. The render runs in
CI (`cd.yml`) alongside the tunnel-ingress render; provisioning a real
`DISCORD_WEBHOOK_URL` GitHub secret is a prerequisite of the live bring-up.

## Signup notifications

The backend external app (`:8000`) is a **second consumer** of the same
`DISCORD_WEBHOOK_URL`. On each successful registration it posts a best-effort,
fire-and-forget message (`🎉 New user registered: <username>`) to Discord. The
notification is deliberately not observability: it is a product signal, not an
alert, and is implemented as an injected `EventPublisher`
(`BestEffortEventPublisher` + `DiscordUserRegisteredHandler` in
`backend/src/wren/accounts/notifications.py`) fired after the DB commit.

- **Never blocks or fails registration.** After the commit
  `AccountService.register` calls `EventPublisher.publish(...)`, which schedules
  delivery via `asyncio.create_task` and returns; all I/O and every error live in
  the background task. A failed delivery is swallowed and logged as a coarse
  category (`event_delivery_failed` with
  `event_type`/`handler`/`user_id`/`error_type`/`status`), never the webhook URL
  (held as `SecretStr`). A rolled-back signup (duplicate/validation) notifies
  nobody. When the webhook is unset the path is a no-op.
- **Delivery via `docker-compose.deploy.yml`.** Unlike the Alertmanager consumer
  (which reads a CI-rendered config), the backend reads `DISCORD_WEBHOOK_URL`
  straight from its container environment; the deploy overlay passes it through
  with the optional `:-` form so the backend stays bootable when it is absent.

### Shared-channel tradeoff and escape hatch

Routing both consumers to one webhook mixes routine signup chatter with the P0
operational alerts in a single Discord channel. This is acceptable on a
low-signup platform. If the noise grows or an independent on/off is wanted, add
an optional `DISCORD_SIGNUP_WEBHOOK_URL` that overrides the shared webhook for
signup notifications (separate channel + independent kill-switch) and falls back
to `DISCORD_WEBHOOK_URL` when empty. It is intentionally left out of the default
scope to keep the config surface minimal.

## Retention and query guards

Configured as Prometheus command flags in `docker-compose.yml`:

- Retention: `--storage.tsdb.retention.time=3d` and `--storage.tsdb.retention.size=2GB` (whichever hits first).
- Query guards: `--query.max-concurrency=5` and `--query.timeout=30s`, sized for the single-VPS scale envelope.

TSDB persists to the `promdata` named volume.

## Topology

Prometheus, node-exporter, and Alertmanager run on `app-net` alongside the other
first-party services; none is reachable through the tunnel because the Cloudflare
ingress allow-list refuses their surfaces at the edge, not because of network
isolation. The backend is scraped on both its external (`:8000`) and internal
(`:8001`) apps; MCP is scraped on `:9000` in-network, never via `mcp.usewren.com`
(which path-exposes only the PRM document and the `/mcp` transport at ingress).
Alertmanager is additionally gated behind the `tunnels` compose profile (see the webhook note
above); Prometheus and node-exporter are ungated and run in local dev.
