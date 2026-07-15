# Wren E2E (Playwright)

End-to-end tests that drive the **study spine** (register → create → publish →
follow → track) against a live, containerized Wren stack.

## Design

- **Serial, one shared stack.** `workers: 1` + `fullyParallel: false`: every
  test runs against one live stack, deterministically.
- **API seeding + UI smoke.** The spine is seeded and asserted through an
  `APIRequestContext` against the external app (`:8000`); a separate smoke proves
  the frontend image serves the SPA and client routing resolves. Authenticated
  UI flows stay in the API layer so the suite is resilient as frontend source
  evolves.
- **Per-test unique users.** `uniqueUser()` mints a fresh handle/email per call
  so runs never collide.
- **Health pre-flight.** `global-setup.ts` blocks until the frontend and backend
  report healthy, so a slow container start is a clear setup failure, not a
  flaky first test.

The base stack is expose-only (the Cloudflare tunnel is the only ingress in
prod), so `docker-compose.e2e.yml` layers on top to publish the frontend and
backend ports to the host and relax cookies. It is **test-only** and never used
by a real deploy.

## Run it locally

```sh
just setup-e2e   # once: install the runner + chromium
just e2e-up      # build + boot the e2e stack, run migrations
just test-e2e    # run the spine + smoke
just e2e-down    # tear down and drop volumes
```

Ports and origins come from `.env.test` (copy `.env.test.example`); the defaults
match `docker-compose.e2e.yml`.

## In CI

The `e2e` job in `.github/workflows/ci.yml` builds and boots the same stack, runs
pre-traffic migrations, installs the browser, and runs this suite. On failure it
uploads the Playwright report and the stack logs.
