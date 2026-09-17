# Error handling and reporting

Wren keeps application responses, structured logs, Prometheus metrics, and Sentry events as separate contracts. Sentry adds incident context without replacing RFC 9457, OAuth, MCP, or browser behavior.

## Ownership

- Backend request handlers report unexpected 5xx failures once. Mapped routes use their fixed operation and domain. Infrastructure failures use `http.500` and omit the domain.
- OAuth errors below 500 remain protocol responses and are not reported. An OAuth `server_error` reports once through the OAuth handler, then returns its unchanged RFC 6749 response and headers.
- Expected validation, not-found, conflict, and permission outcomes do not create events.
- OAuth cleanup logs every failed sweep. Independent database and upstream classes are limited to one Sentry event per hour. The loop continues after a report failure.
- MCP expected backend problems and authorization failures remain agent-recoverable and produce no Sentry event. Typed transport failures report as `upstream`; unknown tool errors report as `internal`. Existing counters and per-call logs remain unchanged.
- The openapi-fetch reporting middleware owns browser API attempts. It reports each actual 5xx response or network rejection once. Expected sub-500 responses carry `expected="true"` and are dropped before transport. The raw session retry rejection uses the middleware hook so the original error object is rethrown unchanged.
- The Sentry React `ErrorBoundary` owns render failures and displays the minimal fallback. No view, SWR callback, or response-state component reports the same failure.

## Bounded taxonomy

Python and MCP reporters accept only registered operations, eight kinds (`validation`, `not_found`, `conflict`, `permission`, `upstream`, `timeout`, `database`, `internal`), and the closed domains `roadmaps`, `progress`, `accounts`, `oauth`, `skill`, `db`, and `mcp`. Browser reporting uses generated API operations or `render.app` and the kinds `validation`, `upstream`, `internal`, and `network`.

Factories derive operations from route registries, registered MCP tools, or the committed OpenAPI registry. Callers cannot pass resolved URLs, IDs, query values, or arbitrary operation strings. Optional tags are allowlisted and bounded. Invalid required taxonomy emits a value-free `reporting_contract_invalid` diagnostic and skips capture. Invalid optional tags are omitted without logging their values.

Default fingerprints group by operation and kind. Cleanup and MCP bounded sites use fixed per-class fingerprints so different tools or sweeps share one incident while their operation and tool tags remain visible. Each class has its own monotonic hourly limiter. Suppressed events do not suppress occurrence logs or Prometheus counters.

## Privacy and disabled mode

The reporter captures exception types and stack frames but replaces serialized exception values with fixed markers. It removes request objects, headers, cookies, query data, bodies, breadcrumbs, extras, mechanism data, frame locals, and non-Wren contexts. The only deliberate user field is the resolved user ID, set in a temporary scope. The application exception and its cause chain are never mutated.

Sentry logging-event capture, breadcrumbs, tracing, replay, and automatic framework exception capture are disabled. Empty backend or MCP DSNs emit one structured `sentry_disabled` startup record after logging setup and make no transport calls. An empty browser DSN initializes nothing and stays silent.

## Release lifecycle

The three Sentry projects and release families are:

| Project | Release |
|---|---|
| `wren-backend` | `wren-api@<sha>` |
| `wren-mcp` | `wren-mcp@<sha>` |
| `wren-frontend` | `wren-web@<sha>` |

CD prepares exact releases before image builds. Preparation inspects the organization API, creates only absent releases, verifies project association, and accepts a failed create only when a follow-up inspection proves that another attempt created the exact release. Finalization runs after a healthy deploy and is idempotent. A finalized release is reusable for a same-SHA rerun without changing its original release date.

The frontend builder injects Debug IDs and uploads maps with the exact web release before the image push. A per-attempt non-secret cache key prevents credentialed same-SHA reruns from reusing an upload layer. Maps are deleted before the nginx runtime copy.

## Quota keep-list

Keep Sentry for actionable unexpected failures only:

- backend and OAuth 5xx responses;
- typed MCP transport and internal tool failures;
- one hourly report per cleanup failure class;
- browser API 5xx responses, network failures, and render failures.

Keep Prometheus metrics and Discord alerts for availability, rates, and host signals. Do not add tracing or replay at the current scale.

Canonical sources: `shared/wren-common/src/wren_common/`, `backend/src/wren/core/`, `backend/src/wren/oauth/`, `mcp/src/wren_mcp/`, and `frontend/src/observability/sentry/`.
