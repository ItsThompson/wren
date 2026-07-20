# Testing

This guide describes the test layers, how to run each one, the main patterns, and
the high-value targets. It documents the current implemented state.

## Philosophy

- Pure deep modules (the DAG validator, the next-item computation, the projection
  helpers) are exhaustively tested, including property tests.
- Trust boundaries fail closed and are tested for the deny path.
- Cross-package wire contracts are machine-gated, so drift between the backend and
  the MCP server fails a test rather than a request in production.
- The frontend pins its SWR posture and a coverage floor, so test behavior cannot
  drift from production behavior.

## Test layers

| Layer | Scope | Tooling | Command |
|-------|-------|---------|---------|
| Backend unit and integration | Service rules, repositories, routers, OAuth flow, DB integration | pytest, Postgres via testcontainers, 80% coverage gate | `just test-backend` |
| Backend property tests | The DAG validator, patch operations, validation, next, slugs | pytest plus hypothesis | `just test-backend` |
| Frontend unit and component | Components, hooks, the data layer | vitest plus Testing Library, 70% coverage gate | `just test-frontend` |
| Frontend acceptance | The SWR data layer against a mock backend | vitest plus MSW | `just test-frontend` |
| Contract drift | Cross-package header constants and the backend-to-MCP schema mirror | pytest in the `contract/` project | (CI `contract-drift` job) |
| MCP | Tool registration, the internal client, the bearer boundary, the frozen tool-schema snapshot | pytest, 80% coverage gate | `just test-mcp` |
| E2E | The full spine and UI smoke against the running stack | Playwright | `just test-e2e` |

The contract project is the only interpreter where the backend and MCP packages
import together. Run it with `cd contract && uv run pytest`, or let the CI
`contract-drift` job run it.

## Patterns

The examples below are illustrative, not copied source. They show the shape of
each style.

### A pure-module unit test

A pure deep module takes inputs and returns a result, so a test asserts on the
return value with no I/O or mocks.

```python
def test_next_skips_checked_items():
    roadmap = build_roadmap(items=["a", "b"], edges=[("a", "b")])
    progress = build_progress(checked={"a"})
    result = compute_next(roadmap, progress)
    assert [item.id for item in result.items] == ["b"]
```

### An MSW-backed hook test

A data-layer test renders a hook through the provider stack and serves the REST
response from an MSW handler, so the test pins the real client contract.

```tsx
it("returns the dashboard body", async () => {
  server.use(http.get("*/me/dashboard", () => HttpResponse.json(dashboard)));
  const { result } = renderHook(() => useDashboard(), { wrapper: renderWithProviders });
  await waitFor(() => expect(result.current.data).toEqual(dashboard));
});
```

### A route-coverage assertion

Every mounted product route needs a `route_registry.py` entry per app. The
coverage test cross-checks the mounted routes against the registry in both
directions, so an undeclared route fails deny.

```python
def test_every_mounted_route_is_declared():
    missing = verify_route_coverage(app, registry)
    assert missing == set()
```

Canonical source: `backend/tests/`.

## High-value targets

| Priority | Target | Focus |
|----------|--------|-------|
| High | The DAG validator | Property tests over graph shapes; cycles and ordering |
| High | Route coverage | `test_route_registry.py`; an undeclared route fails deny |
| High | Schema mirror and header constants | `contract/tests/`; cross-package drift fails a test |
| High | Revalidate-after-write | `frontend/src/test/acceptance/`; no stale flash, no extra GET |
| High | Auth boundaries | `require_user` and `require_internal_user` deny paths; the OAuth cleanup reaper |
| Medium | Next-item computation and projections | Server-computed study order, `concise` and `detailed` shapes |

## End-to-end scenarios

The Playwright spine drives the full stack. The scenarios cover:

| Scenario | Path |
|----------|------|
| Register | A human registers in the SPA |
| Agent OAuth connect | An agent walks the 401, PRM, AS authorize, and token flow |
| Author to publish | An agent creates a draft, validates, and publishes it |
| Follow and study | A human follows a published roadmap and reads the next node |

Canonical source: `e2e/tests/`.

## Coverage gates

| Suite | Floor | Enforced by |
|-------|-------|-------------|
| Backend | 80% | `just test-backend` (pytest config) |
| MCP | 80% | `just test-mcp` (pytest config) |
| Frontend | 70% | `just test-frontend` (`vite.config.ts` thresholds) |

A run below a floor fails locally and in CI.

## Cross-references

- Commands and local setup: `docs/development.md`.
- CI jobs and gates: `docs/ci-cd.md`.
