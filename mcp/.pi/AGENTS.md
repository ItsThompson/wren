# MCP agent guide

Scope: the wren MCP server package (`mcp/`). This file records the durable,
code-verified traps for the MCP Resource Server, the commands for the area, and
its rules. Read it before changing MCP code.

The MCP server is a thin dispatcher and an OAuth 2.1 Resource Server. It imports
no backend code and forwards every tool call to the backend internal app. See
`docs/mcp.md` for the transport, tool catalog, and boundary contract, and
`docs/auth.md` for the token model.

## Commands

All recipes run from the repo root and change into `mcp/`.

| Command | Purpose |
|---------|---------|
| `just setup-mcp` | Install dependencies from `uv.lock` |
| `just dev-mcp` | Run the RS (`:9000`) with autoreload; the MCP Inspector attaches here |
| `just test-mcp` | Run the test suite with coverage |
| `just lint-mcp` | Ruff check, format check, and mypy |
| `just fmt-mcp` | Format and autofix |
| `just sync-skill` | Re-sync the backend-bundled `SKILL.md` after editing the root copy |

## Separation from the backend

- The MCP image must not import backend code. Shared truths are duplicated on
  purpose and guarded by `contract/tests/`. Change both sides together. See
  `docs/infra-duplication.md`.
- Header-name constants in `config.py` (`USER_ID_HEADER`, `INTERNAL_TOKEN_HEADER`)
  and `REQUEST_ID_HEADER` in `client.py` must match the backend
  `wren.core.identity` and `wren.core.correlation`. The `contract-drift` job
  enforces it. MCP-only tests compare the constant to itself and cannot catch
  backend drift.
- `schemas.py` mirrors the backend authoring and read projections. The
  schema-mirror test (`contract/tests/test_schema_mirror.py`) enforces field
  equality. Editing a schema here without the backend breaks the mirror.
- `logging.py` is code-identical to the backend copy. `metrics.py` and `health.py`
  differ only at a named point. Apply any change to both copies.
- Mirror any change to the HTTP-metric families in `metrics.py` to
  `backend/src/wren/core/metrics.py`. `health.py` is a hand-maintained copy plus
  `jwks_readiness_check`.
- `configure_logging` is a once-per-process no-op after the first call. Do not
  rely on a second call to change the level or renderer.

## The internal hop

- Never forward the agent bearer token downstream. Only the resolved `user_id`
  crosses the internal boundary. Adding token forwarding breaks the
  confused-deputy defense.
- Set the trusted headers last. In `client._request`, do not set `X-User-ID` or
  `X-Internal-Api-Token` through `extra_headers`. The method overwrites them last
  so a caller cannot spoof identity.
  Test: `test_extra_headers_cannot_override_the_trusted_identity`.
- The RS always mints a fresh `request_id`. It never honors an inbound
  `X-Request-ID` from the agent surface.
- The internal client timeout is bounded at 10 seconds.
- Client method names mirror the internal router ops 1:1. Preserve this when you
  add a tool.

## Auth and tokens

- Never derive an issuer, audience, or URL from the request host. Use pinned
  `RsSettings`. The RS sits behind the tunnel, so a request-derived value breaks
  token validation (the site-URL gotcha).
- Audience binding is the confused-deputy defense. A validly signed token minted
  for a different resource is rejected because its `aud` is not this RS.
- `verify()` returns `None` on any failure (bad signature, wrong `iss` or `aud`,
  expiry, no `sub`). Treat `None` as reject-401. It does not raise.
- `get_request_agent` fails closed. A tool reached without the guard raises
  `unauthenticated`, never an unchecked value.
- Only `/mcp` is bearer-guarded. The PRM and health endpoints are public by
  design (`BearerAuthMiddleware._is_protected`).
- `SUPPORTED_SCOPES` (`config.py`) must mirror the backend AS supported scopes.
  They are kept in sync by contract, not shared code.
- An unknown `kid` triggers a single JWKS refetch, throttled by a cooldown and a
  lock, so a stream of unknown-`kid` tokens cannot hammer the AS.

## Tools

- Every new tool registers through `counted_tool_registrar` and opens with
  `require_scope`. That is the uniform metrics and authorization contract.
- `require_scope` is the only sanctioned source of `user_id` inside a tool. Never
  accept a user id as a tool argument.
- `progress_update` lives in `tools_read.py` but requires `progress:write`, not
  `roadmaps:read`. Do not infer a tool's scope from its file.
- Update the frozen schema snapshot (`mcp/tests/snapshots/tools_schema.json`) when
  you add or change a tool. The snapshot test fails otherwise.
- There is no visibility, archive, or delete tool. Those are web-only.

## Transport and serving

- Keep the two explicit `/mcp` and `/mcp/` routes. A `Mount` reintroduces a 307
  redirect that stalls https-to-http MCP clients for about 30 seconds.
- Call `mcp.streamable_http_app()` once during assembly. It creates the session
  manager as a side effect. The `session_manager` property raises otherwise.
- `mcp.usewren.com` exposes only the PRM document and `/mcp` at ingress. Scrape
  `/metrics` and poll health in-network on `:9000` only.
- CORS is dev-only (the MCP Inspector). `ProxyHeadersMiddleware` is prod-only and
  trusts only the pinned app-net CIDR, never `*`.

## Cross-surface facts

- The authoring guidance (`SKILL.md`) is served by the backend, not the MCP
  server. The backend external app serves it at `GET /skill` on its API origin
  (the AS host). The tool docstrings point the agent there. The MCP server serves
  only the PRM document and `/mcp` at ingress. Do not imply the MCP server serves
  `/skill`.
- The deadline is web-only by deliberate, tested design. There is no MCP deadline
  tool. `progress_get` reads the deadline; `progress_update` writes progress. The
  backend `DeadlineRequest` and `Progress` types are deliberately unmirrored in
  the MCP contract, asserted by `contract/tests/test_schema_mirror.py`. Do not add
  a deadline tool without changing that contract.
- Following is created implicitly by the first progress write, the same on the web
  and MCP. There is no follow or unfollow MCP tool. The internal `POST /follow`
  route is vestigial and no MCP client method calls it. Do not imply a follow
  tool exists.

## Rules

- `skill/SKILL.md` (repo root) and the backend-bundled copy must stay
  byte-identical. Run `just sync-skill` after editing the root copy.
- Pin every externally visible URL from `RsSettings`, never from a request.
- Keep the tool bodies thin: one scope check, one internal call, one validation
  into a frozen projection.
