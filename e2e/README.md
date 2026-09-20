# Wren E2E

The E2E suite verifies production-facing Wren behavior through trusted HTTPS. It uses Chromium, the official MCP TypeScript client, the real frontend, backend, MCP server, Postgres, and a local recorder. It reproduces Wren's public host, cookie, origin, callback, and forwarded-header contracts. It does not emulate Cloudflare.

## Topology

Only nginx publishes a host port. The E2E stack contains exactly six services:

| Service | Role | Network exposure |
|---|---|---|
| `ingress` | nginx HTTPS entry point | Publishes host port `443` only |
| `frontend` | React SPA | Compose network, port `80` |
| `backend` | External and internal FastAPI listeners | One container with ports `8000` and `8001` on the Compose network |
| `mcp` | OAuth-protected MCP resource server | Compose network, port `9000` |
| `postgres` | Disposable test database | Compose network only |
| `recorder` | Local browser-envelope receiver and safe export API | Compose network, port `8080` |

The external backend listener serves REST and OAuth routes. The internal listener serves MCP tool calls. They are two listeners in one backend container, not separate containers. nginx-to-origin traffic and MCP-to-internal-backend traffic use HTTP inside Compose. MCP uses HTTPS through nginx for `api.wren.test` authorization metadata and JWKS.

The public hosts are fixed:

| Host | Public contract |
|---|---|
| `https://app.wren.test` | SPA, browser consent pages, and recorder paths under `/_e2e/` |
| `https://api.wren.test` | REST and OAuth authorization-server routes; public `/healthz`, `/readyz`, and `/metrics` are denied |
| `https://mcp.wren.test` | Public protected-resource metadata and bearer-protected `/mcp` transport |

The ingress denies application paths outside these contracts. Frontend, backend, MCP, Postgres, and recorder ports are not published to the host.

## Prerequisites

Install Docker, Node.js 22, `just`, and `mkcert`. Chromium is installed by `just setup-e2e`. macOS setup uses the local mkcert trust integration. Ubuntu setup installs the required browser dependencies in CI and requires the privileges needed to update `/etc/hosts` and install the isolated local CA. Setup supports macOS contributor workstations and Ubuntu CI hosts.

Use only the trusted HTTPS ingress. Do not disable certificate verification, publish service ports, use development cookies, or send telemetry to a real Sentry host.

## Clean-workstation workflow

Run these commands in order:

```sh
just setup-e2e          # Install E2E dependencies, Chromium, hosts, CA, and OAuth key
just test-e2e-unit      # Run Vitest unit and harness tests without Compose
just e2e-up             # Migrate Postgres, start the six-service topology, and wait for readiness
just test-e2e           # Run typecheck, lint, Vitest, and the full Playwright suite
just e2e-logs           # Show ingress, frontend, backend, MCP, Postgres, and recorder logs
just e2e-down           # Stop containers, remove networks and volumes, and remove generated OAuth material
just reset-e2e-trust     # Remove only Wren-managed hosts and certificate material
```

`just setup-e2e` is idempotent. It maps `app.wren.test`, `api.wren.test`, and `mcp.wren.test` to the local ingress, creates an isolated Wren mkcert `CAROOT`, issues a certificate covering all three names, verifies OS and Node trust, and generates test-only OAuth signing material. It does not modify unrelated host entries or certificate authorities.

`just e2e-up` starts Postgres, runs the migration before application traffic, builds the focused dependency graph, starts nginx, and waits for these HTTPS checks: the SPA root, API authorization-server metadata, MCP protected-resource metadata, MCP container JWKS health, and recorder readiness. A failed check names its boundary and blocks tests.

Use `just test-e2e-system` when the stack is already running and only the Playwright suite should run. Use `just e2e-typecheck`, `just e2e-lint`, and `just test-e2e-unit` to run individual static or harness gates. Use `just e2e-capture-artifacts` while the stack and recorder remain available to create the sanitized diagnostic bundle.

Teardown is safe after a failed or interrupted run. Run `just e2e-down` before `just reset-e2e-trust` when the disposable stack is no longer needed. Trust reset removes only the Wren-managed host block, isolated CA, and leaf certificate.

## Official MCP client flow

Agent scenarios use the official MCP TypeScript SDK. The client starts without a token, discovers protected-resource metadata from `https://mcp.wren.test`, discovers the authorization server at `https://api.wren.test`, and performs dynamic client registration with an attempt-specific loopback callback. The SDK owns PKCE with `S256`.

Chromium opens the real consent page at `api.wren.test`. The test verifies the client name and requested scopes, approves consent through visible controls, validates the loopback callback state, finishes authorization, creates a fresh transport, and completes MCP initialization. Successful journeys call tools through the SDK public methods. They do not handcraft `initialize`, `tools/list`, or `tools/call` JSON and do not approve consent through a direct API request.

E2E access tokens live for two seconds. The refresh journey waits from the recorded expiry with a bounded poll and verifies that a later tool call succeeds while the grant remains active. The revocation journey removes the connection through the browser, waits for expiry, and verifies that refresh fails. Issued access JWTs are not expected to fail before expiry. Tokens, refresh credentials, authorization codes, PKCE verifiers, and synthetic passwords never enter logs or artifacts.

## Recorder and recovery

The frontend uses the real browser SDK with the local DSN `https://e2epublickey@app.wren.test/_e2e/sentry/1`. The SDK sends envelopes to `https://app.wren.test/_e2e/sentry/api/1/envelope/`, which nginx routes to `recorder`. The recorder is append-only. Tests query by attempt identity and the stable operation and failure-kind tags, so concurrent tests never use a global reset or the latest event.

Recovery tests inject one dashboard HTTP 500 and one connected-agents network failure through Playwright routing. They assert the existing retry UI, successful recovery, and a matching serialized envelope. Backend and MCP Sentry DSNs are empty in this topology. The recorder control token protects readiness, queries, and safe export; it is never placed in the frontend bundle.

`just e2e-capture-artifacts` captures the HTML report, first-retry traces, failure screenshots, safe attachments, six service logs, and a sanitized recorder projection. The sanitizer redacts registered synthetic values and sensitive request fields, scans the rebuilt files, and fails closed by withholding the bundle when safety is not provable. Raw envelopes, private keys, cookies, tokens, passwords, and request bodies are not uploaded.

## Concurrency and retries

Local runs use one worker and zero retries for focused debugging. CI uses one shared stack, two workers, `fullyParallel: false`, Chromium, one retry, and a trace on the first retry. Tests inside one file retain explicit ordering, while files can run concurrently.

Fixtures own every custom browser context, API context, callback listener, MCP session, and recorder query. Accounts, roadmaps, OAuth clients, and event identities include the run, worker, retry, test identity, and a nonce. A retry receives fresh attempt data. Specs do not depend on an empty database, recorder order, process-global state, or another test's success.

## Artifacts and logs

Local Playwright output uses `e2e/playwright-report/` when an HTML report is generated and `e2e/test-results/` for traces, screenshots, and attachments. CI uploads `/tmp/wren-safe-artifacts/` only after the safety scan succeeds, with seven-day retention. The bundle includes separate logs for ingress, frontend, backend, MCP, Postgres, and recorder. Run `just e2e-logs` for live Compose logs without direct service ports.

## Troubleshooting

| Symptom | Check |
|---|---|
| Host or certificate setup fails | Run `just setup-e2e` again and inspect the named `hosts`, `tls-san`, `os-trust`, or `node-trust` check. Keep the three exact `.wren.test` names and do not add a TLS bypass. |
| Browser or Node rejects HTTPS | Confirm the isolated Wren CA exists and `NODE_EXTRA_CA_CERTS` points to `e2e/ingress/certificates/caroot/rootCA.pem` before Node starts. |
| Secure cookies or CORS fail | Use `https://app.wren.test` and `https://api.wren.test`; do not use localhost, direct ports, or HTTP. The E2E backend runs with `ENVIRONMENT=production` and `.wren.test` cookies. |
| OAuth callback fails | Keep the loopback listener owned by the fixture, use the generated callback, and complete consent in Chromium. Do not reuse state or call the authorize endpoint directly. |
| Readiness fails | Run `just e2e-logs`. Check migration output, SPA root content, API metadata, MCP PRM and JWKS trust, recorder readiness, and the six-service allowlist. |
| Migration fails | Fix the migration or database startup error before running tests. `just e2e-up` never starts Playwright after a failed migration. |
| Recorder matching fails | Query by the test attempt and operation tags. Do not clear the recorder globally or select its latest envelope. |
| A direct port is reachable | Stop the stack and inspect Compose. Only nginx may publish host port `443`; application, database, and recorder ports stay private. |
| Teardown leaves generated material | Re-run `just e2e-down`, then `just reset-e2e-trust`. The cleanup command continues OAuth-key and control-token removal after partial failures. |

See `docs/testing.md` for ownership boundaries, `docs/development.md` for inner-loop setup, and `docs/ci-cd.md` for the required CI gate.
