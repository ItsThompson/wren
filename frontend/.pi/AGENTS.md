# Frontend agent guide

Scope: the wren frontend package (`frontend/`). This file records the durable, code-verified traps for the frontend, the commands for the area, and its rules. Read it before changing frontend code.

The frontend is a React 19 SPA that talks to the backend external app over a typed REST client. See `docs/frontend.md`, `docs/design-language.md`, `docs/api.md`, and `docs/auth.md`.

## Commands

All recipes run from the repo root and change into `frontend/`.

| Command | Purpose |
|---------|---------|
| `just setup-frontend` | Install dependencies (`npm install`) |
| `just dev-web` | Run the SPA against the real backend |
| `just dev-mock` | Run the SPA against the Mock Service Worker (zero backend) |
| `just test-frontend` | Run the test suite with coverage |
| `just lint-frontend` | Type check (`tsc`) and lint |
| `just codegen` | Regenerate the REST client after any external REST change (CI drift-gates it) |

## Data layer and clients

- Never hand-edit `src/api/schema.d.ts`. Regenerate it with `just codegen` after `openapi.json` changes. CI drift-gates it.
- Register every read's key in `keys/keys.ts`. Reuse the same builder for the write-side `mutate()`, or the cache entry will not match.
- Prefer `useApiQuery` and `usePublicApiQuery` over a raw `client.GET`. Use `usePublicApiQuery` only for a genuinely credential-free read. Today only the profile read qualifies.
- Pass a `null` key to disable a read. Do not wrap the hook in an `if`.
- Reconcile a write into the same `keys.*` entry the reads use, with `mutate(returned, { revalidate: false })`. The list and tree share `keys.roadmap(id)` and `keys.progress(id)`.
- The 401 refresh-and-retry replays bodyless requests only. A body-consuming write cannot rely on transparent retry.
- The refresh middleware skips the `/auth/` prefix. Do not route other endpoints under `/auth/` unless you want them refresh-exempt.
- Read `VITE_API_BASE_URL` only at the app root. Read `VITE_MCP_BASE_URL` only at the `OnboardingView` root and thread it as props.
- The `Problem` type mirrors the backend `ErrorCode`. Types alias the generated `components['schemas']`. Do not add TS enums; `erasableSyntaxOnly` forbids them.

## Components and tokens

- Keep the CSS import order in `main.tsx`: `fonts.css`, then `tokens.css`, then `globals.css`. `globals.css` reads token variables, so it must come last.
- Add new token values to `shared/theme/tokens.css` only. `globals.css` maps them, never defines them. Never re-declare token values in `globals.css`.
- Do not reorder `TAG_PALETTE` or change `hashString` in `lib/tag-color`. The index a tag hashes to is a frozen cross-view contract mirrored in `tokens.css`.

## Testing

- vitest enforces a 70% line coverage floor (`vite.config.ts`). A drop below the floor fails the build.
- Match colon-action endpoints (`:publish`, `:archive`) by concrete URL in tests. `path-to-regexp` treats the second colon as a param.
- MSW handler paths must stay `*`-prefixed so they match any API base.
- Use `renderWithProviders` when a component reads data or auth through the stack. Use `renderWithAuth` for pure chrome. Do not build a bespoke provider tree per test.
