# Architecture

Wren is a learning-roadmap platform for two kinds of user. Humans use a React SPA. AI agents use an MCP server. Both reach one backend, so the rules for creating, publishing, and tracking roadmaps live in one place.

This guide describes the system shape, the component roles, the trust zones, and the request flows. It documents the current implemented state and cites canonical source paths instead of copying code.

## System shape

The system is one backend that serves two apps, one MCP Resource Server, one React SPA, one PostgreSQL database, and one Cloudflare tunnel for ingress.

Canonical sources:

- App factory: `backend/src/wren/core/`
- External app entrypoint: `backend/src/wren/api/`
- Internal app entrypoint: `backend/src/wren/api_internal/`
- MCP RS assembly: `mcp/src/wren_mcp/`
- Container topology: `docker-compose.yml`

## Topology

```mermaid
graph TB
  subgraph edge["Cloudflare tunnel (ingress)"]
    human["Human browser"]
    agent["AI agent"]
  end
  subgraph appnet["app-net"]
    fe["Frontend SPA (:80)"]
    ext["External app :8000"]
    int["Internal app :8001"]
    mcp["MCP RS :9000"]
    prom["Prometheus"]
  end
  subgraph datanet["data-net"]
    pg[("PostgreSQL")]
  end
  human -->|"HTTPS"| fe
  human -->|"HTTPS + session cookie"| ext
  agent -->|"HTTPS + Bearer token"| mcp
  mcp -->|"X-User-ID + INTERNAL_API_TOKEN"| int
  mcp -->|"JWKS verify"| ext
  ext --> svc["Shared service layer"]
  int --> svc
  svc --> pg
  prom -->|"scrape /metrics"| ext
  prom -->|"scrape /metrics"| int
  prom -->|"scrape /metrics"| mcp
```

Two Docker bridge networks separate the tiers. `app-net` carries every first-party service. `data-net` isolates PostgreSQL; the backend is the only service on both. The tunnel is the only ingress and opens no inbound host port.

## Component roles

| Component | Role | Canonical source |
|-----------|------|------------------|
| External app (`:8000`) | Internet-facing. Authenticates humans by session cookie. Hosts the public REST API and the OAuth 2.1 authorization server. | `backend/src/wren/api/` |
| Internal app (`:8001`) | App-net only. Trusts an injected `X-User-ID` header behind `INTERNAL_API_TOKEN`. Mounts the roadmap and progress routers over the same service layer. Never mounts the web-only lifecycle routes. | `backend/src/wren/api_internal/` |
| MCP Resource Server (`:9000`) | The agent front door. An OAuth 2.1 Resource Server that verifies the agent bearer token, then forwards each tool call to the internal app. Carries no backend domain dependency; shares infra via `wren-common`. | `mcp/src/wren_mcp/` |
| Frontend SPA (`:80`) | The React app for humans. Talks to the external app over a typed REST client. Served by nginx in the container. | `frontend/` |
| PostgreSQL | The single datastore. Reached by the backend over an async connection pool. | `docker-compose.yml` |
| Observability | Prometheus scrapes `/metrics` on all apps in-network. node-exporter reports host metrics. Alertmanager routes alerts to Discord. | `docs/monitoring.md` |

Both apps come from `create_app`. They differ only by injected settings and by which routers and identity dependency they mount.

## Isolation and trust zones

| Zone | Reachable from | Identity model | Must never |
|------|----------------|----------------|------------|
| External app (`:8000`) | Internet via the tunnel | Session cookie; strips any inbound `X-User-ID` app-wide | Trust a client-supplied `X-User-ID` |
| Internal app (`:8001`) | app-net only | Trusted `X-User-ID` behind `INTERNAL_API_TOKEN` | Be tunnel-routed or host-published |
| MCP RS (`:9000`) | Internet via the tunnel | Agent Bearer token, audience-bound | Forward the agent token downstream, or serve any path but PRM and `/mcp` at ingress |
| Data tier | app-net (data-net) only | Connection pool credentials | Be reachable from the edge |

Every request resolves to exactly one `user_id`, and the server never trusts one from a request body or a tool argument. See `auth.md` for how each boundary resolves identity and fails safe.

## Design decisions

| Decision | Rationale |
|----------|-----------|
| One factory, two apps | The external and internal apps share one service layer and differ only by injected settings and the per-app route registry (which routes mount and the identity each resolves), so a rule is defined once. |
| Backend/MCP boundary | The two are separate deployables. The MCP shares no backend DOMAIN code and carries no backend dependency. Shared INFRA (logging, metrics, health) lives in the `wren-common` workspace package. The agent-facing Group-A schemas are generated from the internal app's OpenAPI document (`just codegen-mcp`), so they cannot drift; the remaining wire truths (headers, scopes, lean write results) stay mirrored and are gated by `contract/tests/`. A backend-internal schema change cannot silently mutate the agent-facing contract. See `docs/packaging.md`. |
| Fail-safe deny at every boundary | An empty `SESSION_JWT_SECRET` denies all sessions; an empty `INTERNAL_API_TOKEN` denies all internal calls; a missing state seam degrades to deny. |
| 404 over 403 | The service returns 404 for a private resource, so a caller never learns a resource exists but is off-limits. |
| Site-URL pinning | All OAuth issuer, metadata, and endpoint URLs build from pinned config, never from the request host, because the tunnel reaches the origin over an internal URL. |
| Pure-ASGI correlation middleware | `BaseHTTPMiddleware` runs the handler in a separate contextvars context, so the `request_id` binding would be invisible to the handler and the 500 log. |
| Document-plus-write-derived index | A roadmap's `document` JSONB is authoritative; scalar columns are write-derived, so reads stay cheap and the source of truth stays single. |

## Request flows

The detailed sequence diagrams live with the domain that owns each flow:

- Human session request (cookie verify, `sid` blacklist lookup, strip middleware): see `auth.md`.
- Agent OAuth token acquisition (register, authorize, consent, token, refresh): see `auth.md`.
- Agent tool call (bearer verify, the RS-to-internal hop, confused-deputy defense): see `mcp.md`.

## Cross-references

- Trust boundaries and the OAuth model: `docs/auth.md`.
- Storage ownership and the roadmap lifecycle: `docs/data-model.md`.
- REST route catalog and the error contract: `docs/api.md`.
- MCP transport and the internal-hop contract: `docs/mcp.md`.
- Metrics, alerts, and retention: `docs/monitoring.md`.
