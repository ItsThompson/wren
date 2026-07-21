# REST API reference

This reference catalogs the wren backend REST surface, the shared response contracts, and the error contract.

Canonical sources:

- Access map (machine-checked): `backend/src/wren/core/`
- Domain wire schemas: `backend/src/wren/roadmaps/`, `backend/src/wren/progress/`, `backend/src/wren/oauth/`, `backend/src/wren/accounts/`
- Error contract: `backend/src/wren/core/`, `backend/src/wren/oauth/`
- Generated client contract: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

The Pydantic schema modules are the single source of truth for the wire shapes. The frontend consumes them as OpenAPI-generated TypeScript. Run `just codegen` after any external REST change; CI drift-gates the generated client.

## Two apps and access levels

The backend serves two apps from one factory. The external app (`:8000`) is internet-facing. The internal app (`:8001`) is app-net only and is the MCP server's only intended caller. See `architecture.md` for the split and `auth.md` for the trust boundaries.

Every mounted product route declares an access level in `route_registry.py`. A coverage test cross-checks the mounted routes against the registry in both directions and fails deny if a mounted route has no entry. So an unscoped endpoint cannot ship.

| Access level | Meaning |
|--------------|---------|
| `PUBLIC` | No authentication (landing metadata, profile, `/skill`, `/auth/*`). |
| `EXTERNAL_COOKIE` | `require_user`: the human session cookie. |
| `INTERNAL_TRUSTED` | `require_internal_user`: the trusted `X-User-ID` behind `INTERNAL_API_TOKEN`. |
| `OAUTH` | The OAuth 2.1 AS handshake surface (unauthenticated protocol endpoints). |

The same path can carry different levels on the two apps. For example `POST /roadmaps` is `EXTERNAL_COOKIE` on `:8000` and `INTERNAL_TRUSTED` on `:8001`.

## Route groups

| Group | Prefix | External `:8000` | Internal `:8001` |
|-------|--------|------------------|------------------|
| Accounts sessions | `/auth` | `PUBLIC` | not mounted |
| Onboarding + dashboard | `/me` | `EXTERNAL_COOKIE` (profile is `PUBLIC`) | not mounted |
| Roadmaps authoring and reads | `/roadmaps` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Roadmaps web-only lifecycle | `/roadmaps` | `EXTERNAL_COOKIE` | not mounted |
| Progress | `/roadmaps/{id}` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| OAuth 2.1 AS | various | `OAUTH` / `EXTERNAL_COOKIE` | not mounted |
| Skill guidance | `/skill` | `PUBLIC` | not mounted |
| Health and metrics | `/healthz`, `/readyz`, `/metrics` | not in schema | not in schema |

Health and metrics routes mount with `include_in_schema=False`, so the coverage check excludes them by construction. See `monitoring.md` for `/metrics`.

## Roadmaps endpoints

Each route's mounting app and access level are declared in `route_registry.py`;
the roadmaps factory reads that table, so a route mounts on an app only when the
registry lists it for that app. The web-only lifecycle routes (visibility,
archive, delete) are declared for the external app only, so they have no internal
route and no MCP tool.

| Method and path | Purpose | Notes |
|-----------------|---------|-------|
| `POST /roadmaps` | Create a draft | 201, returns `RoadmapCreated` with a `proposed_id -> minted_id` remap |
| `GET /roadmaps/{id}` | Full document | Owner any status; non-owner only a public published or archived roadmap |
| `GET /roadmaps/{id}/overview` | Orientation counts | `format=concise\|detailed` |
| `GET /roadmaps/{id}/nodes/{sid}` | One subsection | Unknown id returns 404 naming the valid siblings |
| `GET /roadmaps/{id}/sections/{sid}` | Paginated drill-down | `cursor` (opaque), `include=subsections\|items\|both` |
| `GET /roadmaps/{id}/search` | Search subsections and items | `q` and `tags`; empty query with no tags returns `[]` |
| `PATCH /roadmaps/{id}` | Iterative edit | `If-Match` header; atomic op list. See the deep spec below |
| `PUT /roadmaps/{id}` | Full-document import escape hatch | `If-Match`; re-mints, preserves the roadmap id, owner, created_at, visibility |
| `POST /roadmaps/{id}:validate` | All violations, no mutate | Always 200 with a (possibly empty) `violations` list |
| `POST /roadmaps/{id}:publish` | draft to published | 422 hard-block on any violation |
| `POST /roadmaps/{id}:fork` | New draft from a readable source | 201; no progress carry-over |
| `PATCH /roadmaps/{id}/metadata` | Presentation-only edit | Allowed post-publish; not `If-Match`-guarded |
| `PUT /roadmaps/{id}/visibility` | Toggle public or private | Web-only |
| `POST /roadmaps/{id}:archive` | Retire a published roadmap | Web-only |
| `DELETE /roadmaps/{id}` | Delete | Web-only; 409 `DELETE_HAS_FOLLOWERS` when any follower exists |
| `GET /me/dashboard` | Private dashboard (authored + followed) | External only, `require_user` |
| `GET /users/{handle}` | Public profile | External only, `PUBLIC` |

See `authoring.md` for the authoring rules and the immutability boundary. See `data-model.md` for the roadmap lifecycle.

## Progress endpoints

Under the `/roadmaps/{id}` resource. Snapshot, explicit-set, and next mount on
both apps; follow and deadline mount on the external app only (see the
internal-surface note).

| Method and path | Purpose | Notes |
|-----------------|---------|-------|
| `POST /roadmaps/{id}/follow` | Start following | 201, idempotent. See the internal-surface note |
| `GET /roadmaps/{id}/progress` | Snapshot | `detailed=true` adds `checked_ids` |
| `POST /roadmaps/{id}/progress` | Explicit-set items | Returns the snapshot plus the next suggestion |
| `GET /roadmaps/{id}/next` | Server-computed next items | `format=concise\|detailed` |
| `PUT /roadmaps/{id}/deadline` | Set (a date) or clear (null) the deadline | See the internal-surface note |

Internal-surface note: `POST /follow` and `PUT /deadline` mount on the external app only; the internal app the MCP server calls does not mount them, so both return 404 there. `POST /follow` is called by no client: following is created implicitly by the first progress write. `PUT /deadline` is web-only, and its `DeadlineRequest`/`Progress` types are unmirrored in the MCP contract (`contract/tests/`), so there is no MCP deadline tool. See `progress.md` for the follow and study-loop semantics.

## OAuth, accounts, and skill endpoints

External app only. See `auth.md` for the session and OAuth models.

| Method and path | Access | Notes |
|-----------------|--------|-------|
| `POST /auth/register` | `PUBLIC` | 201; sets both cookies; returns `AuthenticatedUser` |
| `POST /auth/login` | `PUBLIC` | Generic 401 on any credential mismatch |
| `POST /auth/refresh` | `PUBLIC` | Reads `wren_refresh`; rotates the session |
| `POST /auth/logout` | `PUBLIC` | 204; revokes the `sid`; clears cookies |
| `POST /me/onboarding:complete` | `EXTERNAL_COOKIE` | No body; idempotent |
| `GET /.well-known/oauth-authorization-server` | `OAUTH` | RFC 8414 metadata, `no-store` |
| `GET /jwks` | `OAUTH` | Public JWKS, `no-store` |
| `POST /register` | `OAUTH` | RFC 7591 Dynamic Client Registration |
| `GET /authorize` | `OAUTH` | 302 to the SPA consent page with `auth_request_id` |
| `GET /authorize/context` | `OAUTH` | Consent context (optional session) |
| `POST /authorize/decision` | `EXTERNAL_COOKIE` | The consent decision |
| `POST /token` | `OAUTH` | Both grant types; `no-store` |
| `POST /revoke` | `OAUTH` | RFC 7009 refresh-token revoke; `no-store` |
| `GET /me/clients` | `EXTERNAL_COOKIE` | The user's connected agents |
| `DELETE /me/clients/{client_id}` | `EXTERNAL_COOKIE` | 204; revoke a grant |
| `GET /skill` | `PUBLIC` | Serves the bundled `SKILL.md` as `text/markdown` |


## Deep spec: `PATCH /roadmaps/{id}`

The iterative edit path. It applies an ordered list of atomic operations under optimistic concurrency.

- Request body: `PatchRequest` with `operations`, at least one op. Every op addresses nodes by slug id, never by array index. Ordering uses `before_id` and `after_id`. The `op` string discriminates the union (16 op types), which surfaces to the client as an OpenAPI `oneOf`.
- Concurrency: the target `revision` travels in the `If-Match` header, not the body. A missing or malformed header is a FastAPI `422`.
- Atomicity: `patch.apply` runs over a deep copy. Any op failure raises and nothing is persisted (all-or-nothing). Acyclicity is re-checked after each edge-affecting op, so a batch that creates a transient cycle is rejected even when the final graph is acyclic.
- Success: `revision` bumps by one. The response is a `PatchResult` with the changed nodes and a `proposed_id -> minted_id` remap for any de-duped `add_*` op.

| Outcome | Status | Code |
|---------|--------|------|
| Stale `If-Match` revision | 409 | `STALE_REVISION` |
| Write against a published or archived roadmap | 409 | `IMMUTABLE` |
| Invalid op (unknown id, cycle-creating edge) | 422 | `VALIDATION` |
| Non-owner or unknown roadmap | 404 | `NOT_FOUND` |

## Error contract

Every service-layer fault raises a `WrenError` subclass. One exception handler maps the whole hierarchy to RFC 9457 `application/problem+json`, so every transport (external REST, internal REST, MCP over internal REST) emits one error shape. FastAPI's `RequestValidationError` maps into the same field-map shape. Never build problem+json by hand.

### Problem body

Media type `application/problem+json`. Members: `type`, `title`, `status`, `code`, `detail`, optional `instance`, `fields`, `violations`. Extension members are omitted from the wire when unset.

### Error codes

`code` is the `ErrorCode` StrEnum. `WrenError` subclasses fix the status and title.

| Code | Status | Meaning |
|------|--------|---------|
| `NOT_FOUND` | 404 | Resource not found (also the 404-over-403 no-existence-leak answer) |
| `UNAUTHORIZED` | 401 | Authentication required or session expired |
| `FORBIDDEN` | 403 | Reserved; not raised in production (the service returns 404 instead) |
| `VALIDATION` | 422 | Request or structural validation failed; may carry a `violations` array |
| `CONFLICT` | 409 | Generic conflict with the current state |
| `STALE_REVISION` | 409 | Optimistic-concurrency mismatch on `If-Match`; re-read and retry |
| `IMMUTABLE` | 409 | Structural write against a published or archived roadmap; fork to change |
| `DELETE_HAS_FOLLOWERS` | 409 | Delete refused because the roadmap has followers; archive instead |
| `INTERNAL` | 500 | Unexpected fault; the body is generic and leaks no stack trace |

Structural violations surface as a `Violation` list (rule id, `ids`, `message`) in both the `validate` 200 body and the `publish` 422 body: one contract for both.

### Two error contracts on the OAuth router

The OAuth router uses two error contracts by design (`oauth/`).

- Agent protocol endpoints (`/register`, `/authorize`, `/token`, `/revoke`) return RFC 6749 `{error, error_description}` JSON that the MCP SDK parses.
- SPA-facing endpoints (`/authorize/context`, `/authorize/decision`, `/me/clients`) return RFC 9457 problem+json.

Do not mix them. Adding an OAuth route means choosing the right error family.
