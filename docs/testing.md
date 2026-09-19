# Testing

This guide defines ownership for each test layer. It keeps system E2E focused on public contracts that lower layers cannot prove alone.

## Test layers and ownership

| Layer | Owns | Tooling and command |
|---|---|---|
| Pure unit | Domain rules, projections, configuration validation, attempt identity, registry differences, envelope parsing, and artifact projections | pytest or Vitest; package-specific commands |
| Property | DAG validation, patch operations, next-item calculation, and slugs | pytest and Hypothesis through `just test-backend` |
| Backend integration | Services, repositories, routers, OAuth, and database behavior | pytest and testcontainers through `just test-backend` |
| Frontend unit and component | Components, hooks, session middleware, data-layer states, and retry UI | Vitest, Testing Library, and MSW through `just test-frontend` |
| Contract and codegen drift | Cross-package headers and scopes, generated clients, Group-A schemas, and lean result subsets | `contract-drift`, `codegen-drift`, and `mcp-codegen-drift` CI jobs |
| MCP integration | Tool registration, internal client, bearer boundary, schemas, and protocol permutations | pytest through `just test-mcp` |
| E2E unit and harness | Fixture ownership, callback lifecycle, OAuth storage, recorder behavior, registry set equality, and sanitizer safety | Vitest through `just test-e2e-unit`; no separate percentage floor |
| System E2E | Public HTTPS, official MCP authorization, browser journeys, persisted effects, concurrent isolation, and browser recovery | Playwright and the official MCP TypeScript client through `just e2e-up` and `just test-e2e` |

Backend and MCP suites retain their existing 80% floors. Frontend retains its existing 70% floor. E2E unit and harness tests have no numeric floor, but every new deep module has direct behavioral tests.

## System E2E boundary

System E2E runs one production-mode Compose topology through trusted HTTPS at `app.wren.test`, `api.wren.test`, and `mcp.wren.test`. It uses nginx, the frontend, one backend container with external and internal listeners, MCP, Postgres, and the local recorder. The listeners are not separate containers. It does not mock the backend, OAuth server, MCP server, database, or frontend API on success paths.

The agent boundary is the official MCP client through `https://mcp.wren.test`, MCP, the internal backend listener, shared services, and Postgres. Agent tests own discovery, browser consent, dynamic registration, PKCE, initialization, refresh, revocation, tool calls, and persisted read-backs. They do not handcraft MCP JSON-RPC or duplicate lower-layer schema and error matrices.

The human boundary is Chromium against `https://app.wren.test` and `https://api.wren.test`. Visible registration, onboarding, consent, navigation, form controls, checklist changes, lifecycle actions, and recovery actions use real browser controls. API helpers may create unrelated setup accounts and perform independent postcondition reads. They may not perform the user interaction under test.

System E2E covers composition, production cookies and origins, forwarded HTTPS, public routing, official-client behavior, stable persisted effects, and browser recovery. Lower layers own detailed REST validation, full schema and annotation snapshots, route and render permutations, pure domain rules, cryptographic claim matrices, cursor boundaries, and exhaustive protocol errors.

## Exact MCP tool coverage

The initialized official client retrieves the advertised tool list through its public SDK method. The immutable scenario registry must contain exactly these 17 names:

```text
roadmap_list
roadmap_get_profile
roadmap_get
roadmap_get_overview
roadmap_get_next
roadmap_get_node
roadmap_get_section
roadmap_search
progress_get
progress_update
create_roadmap_draft
patch_roadmap_draft
replace_roadmap_draft
validate_roadmap_draft
publish_roadmap
fork_roadmap
edit_roadmap_metadata
```

The gate preserves arrays to detect duplicates, compares the advertised and registry name sets in both directions, and fails with sorted missing and unexpected names. A count-only or subset assertion does not satisfy the invariant. Each registered tool has at least one successful official-client call. Writes have a later independent read of their persisted effect. Assertions select stable IDs, state, relationships, counts, and revisions rather than full payload snapshots.

## Fixtures, cleanup, retries, and concurrency

Every custom browser context, API context, callback listener, MCP session, and recorder query belongs to a fixture or resource owner. Owners register resources immediately after creation, close them in reverse order, continue after one close failure, and report aggregate cleanup errors. Cleanup runs after pass, failure, timeout, and retry.

Each attempt has a run ID, test identity, worker index, retry number, and nonce. Accounts, roadmaps, OAuth clients, and recorder tags use that identity. A retry creates fresh attempt data and never depends on deleting rows from its first attempt. Specs do not require an empty shared database, one global account, one global recorder event, or a fixed execution order.

Local debugging uses one worker and zero retries. CI uses two workers against one stack, `fullyParallel: false`, one retry, and a first-retry trace. Files can run concurrently, while a stateful journey keeps its local ordering inside one test.

## Browser recovery and recorder scope

The browser uses the real SDK transport with the local recorder in place of Sentry. Recovery E2E injects one dashboard HTTP 500 and one connected-agents network failure through Playwright routing. It asserts the existing retry UI, recovery, and a matching scrubbed envelope. No E2E request contacts a Sentry-owned host.

The recorder stores append-only envelopes and supports bounded matching by attempt, operation, and failure kind. Tests never clear it globally or select its latest event. Artifact export contains only a sanitized projection. Lower-layer frontend tests continue to own SDK initialization, scrubber behavior, and route or render permutations.

## Commands and runtime target

Use `just setup-e2e`, `just e2e-up`, `just test-e2e`, `just e2e-logs`, `just e2e-down`, and `just reset-e2e-trust` for the documented local workflow. `just test-e2e-unit`, `just e2e-typecheck`, and `just e2e-lint` run E2E gates without starting Compose.

The normal full CI job target is under five minutes excluding runner queue time. CI records complete-job and Playwright-step durations. The initial policy uses one shared stack and no shards. Review sharding when complete-job p95 exceeds 240 seconds, two-worker Playwright p95 exceeds 180 seconds, worker speedup is below 1.3x, shared-stack CPU or database contention repeats, or a scenario requires an incompatible environment.

Canonical sources: `e2e/tests/`, `e2e/fixtures/`, `e2e/agent/`, and `e2e/artifacts/`.

## Cross-references

- Operational E2E setup and troubleshooting: [`e2e/README.md`](../e2e/README.md).
- Development inner loops and production-mode E2E: [`docs/development.md`](development.md).
- Required CI gate and diagnostics: [`docs/ci-cd.md`](ci-cd.md).
