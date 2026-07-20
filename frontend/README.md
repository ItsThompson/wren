# wren frontend

The wren frontend is a React 19 single-page app built with Vite. It serves human
users and talks to the backend external app over a typed REST client.

## Purpose

- Read, publish, fork, and track roadmaps, and manage their lifecycle.
- Authenticate humans with a session cookie and resume the session on load.
- Run the human OAuth consent screen for an AI agent.

The web app does not author roadmap content. Content authoring (create, patch,
replace, validate) has no web UI. An AI agent authors through the MCP server. The
only sanctioned web edit is presentation-only metadata (title, description,
subject tags).

## Stack

| Concern | Tools |
|---------|-------|
| Framework | React 19, React Router, Vite |
| Styling | Tailwind CSS v4, vendored shadcn/ui primitives, shared design tokens |
| Data | SWR, openapi-fetch (a typed client generated from the OpenAPI document) |
| Dev and test | Mock Service Worker, vitest, Testing Library |

## Architecture

- `App.tsx` composes the provider stack: SWR config, the API client provider, the
  auth provider, and the router.
- `routes.tsx` holds the route tree and its two onboarding guards.
- `auth/` owns the session client and the 401 refresh-and-retry flow.
- `api/` is the data layer: cache `keys`, the `runQuery` adapter, and the
  `useApiQuery` and `usePublicApiQuery` hooks.
- `views/` holds the route targets. Each view is a thin orchestrator over one data
  hook.
- `components/` holds the shared component library. `shared/theme/` and
  `globals.css` bridge the design tokens onto Tailwind.

See `../docs/frontend.md` for the full architecture and data flow.

## Setup and run

All recipes run from the repo root and change into `frontend/`.

| Command | Purpose |
|---------|---------|
| `just setup-frontend` | Install dependencies (`npm install`) |
| `just dev-web` | Run the SPA against the real backend |
| `just dev-mock` | Run the SPA against the Mock Service Worker (zero backend) |
| `just test-frontend` | Run the test suite with coverage |
| `just lint-frontend` | Type check (`tsc`) and lint |
| `just codegen` | Regenerate the REST client from the external OpenAPI document |

## Configuration

The frontend reads three build-time variables: `VITE_API_BASE_URL`,
`VITE_MCP_BASE_URL`, and `VITE_MOCK_API`. See `../docs/frontend.md` for what each
does and `frontend/src/vite-env.d.ts` for the types. `.env.example` at the repo
root is the canonical annotated list. Do not duplicate it here.

## Further reading

- Frontend architecture and data flow: `../docs/frontend.md`
- Design language: `../docs/design-language.md`
- REST reference and the error contract: `../docs/api.md`
- Authentication and OAuth: `../docs/auth.md`
- Progress and the study loop: `../docs/progress.md`
