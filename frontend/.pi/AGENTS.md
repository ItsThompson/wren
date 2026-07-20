# Frontend agent guide

Scope: the wren frontend package (`frontend/`). This file records the durable,
code-verified traps for the frontend, the commands for the area, and its rules.
Read it before changing frontend code.

The frontend is a React 19 SPA that talks to the backend external app over a typed
REST client. See `docs/frontend.md`, `docs/design-language.md`, `docs/api.md`, and
`docs/auth.md`.

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

- Never hand-edit `src/api/schema.d.ts`. Regenerate it with `just codegen` after
  `openapi.json` changes. CI drift-gates it.
- Register every read's key in `keys/keys.ts`. Reuse the same builder for the
  write-side `mutate()`, or the cache entry will not match.
- Prefer `useApiQuery` and `usePublicApiQuery` over a raw `client.GET`. Use
  `usePublicApiQuery` only for a genuinely credential-free read. Today only the
  profile read qualifies.
- Pass a `null` key to disable a read. Do not wrap the hook in an `if`.
- Reconcile a write into the same `keys.*` entry the reads use, with
  `mutate(returned, { revalidate: false })`. The list and tree share
  `keys.roadmap(id)` and `keys.progress(id)`.
- The 401 refresh-and-retry replays bodyless requests only. A body-consuming write
  cannot rely on transparent retry.
- The refresh middleware skips the `/auth/` prefix. Do not route other endpoints
  under `/auth/` unless you want them refresh-exempt.
- Read `VITE_API_BASE_URL` only at the app root. Read `VITE_MCP_BASE_URL` only at
  the `OnboardingView` root and thread it as props.
- The `Problem` type mirrors the backend `ErrorCode`. Types alias the generated
  `components['schemas']`. Do not add TS enums; `erasableSyntaxOnly` forbids them.

## Routing and guards

- Both onboarding guards fail open on a missing onboarding flag. Preserve this; it
  is rollback safety, not a bug.
- Keep `/authorize` a direct child of `AppShell`, never inside `OnboardingGate`.
  The exemption is placement-based and `App.test.tsx` covers it.
- Reset action sub-states on a `:roadmapId` change. `RoadmapView` stays mounted
  across roadmap navigation, so a new sub-state in `useRoadmap` must reset in the
  roadmap-change effect or it leaks across roadmaps.
- Onboarding must call `applyUser` before it navigates, or the guard bounces the
  just-onboarded user back into onboarding.
- Consent must navigate the top window (`navigateExternal`), not follow an XHR
  redirect, or the loopback redirect fails CORS.

## Roadmaps and progress

- The web app does not author roadmap content. Create, patch, replace, and
  validate are agent-only through MCP. Do not add a content-editing form. The only
  web edit is presentation-only metadata (`PATCH /metadata`).
- Following is implicit. The first progress write on a published roadmap creates
  the record: checking the first item or setting a deadline starts following.
  There is no follow or unfollow affordance on the web, and unfollow does not
  exist. `POST /roadmaps/{id}/follow` is a vestigial internal endpoint the SPA
  never calls. Do not build a follow button. See `docs/progress.md`.
- The deadline is web-only. `useProgress.setDeadline` calls `PUT /deadline`. The
  MCP contract does not mirror the deadline, so there is no MCP deadline tool. The
  deadline drives a countdown only, never a pacing signal.
- Progress reads are best-effort. Collapse to an empty checked set on failure;
  never make the tree or list fatal on a progress read failure.
- Derive done-state; never store it. `node-state` delegates to `RoadmapView`'s
  `isSubsectionDone`. Do not fork a second done rule.
- A `locked` tree node is presentational only. It stays clickable; do not treat
  it as a navigation block.
- Filter chips filter which subsections render, never the progress bars. Bars
  always reflect full completion.

## Components and tokens

- Keep the CSS import order in `main.tsx`: `fonts.css`, then `tokens.css`, then
  `globals.css`. `globals.css` reads token variables, so it must come last.
- Add new token values to `shared/theme/tokens.css` only. `globals.css` maps them,
  never defines them. Never re-declare token values in `globals.css`.
- Do not reorder `TAG_PALETTE` or change `hashString` in `lib/tag-color`. The
  index a tag hashes to is a frozen cross-view contract mirrored in `tokens.css`.
- Do not hand-edit `components/ui/**`. It is vendored shadcn output, excluded from
  coverage. Wrap it in a Wren component instead.
- Compose the write-contract notices (`StaleRevisionNotice`, `ImmutableNotice`,
  `ViolationList`). Do not use `WarningBanner` directly.
- Never encode a status by color alone. Pair every hue with an icon or text label.
  Component tests assert the text and role, so a color-only change fails.
- `shared/theme/fonts.css` uses bare `@fontsource-variable` specifiers. Alias them
  in `vite.config.ts` and set `server.fs.allow` one level up.
- Barrel exports are inconsistent. `AppShell`, `OnboardingGate`, `RoadmapCard`,
  `RoadmapCardGrid`, `RoadmapViewTabs`, and `states` have an `index.ts`; `badges`,
  `forms`, and `ui` do not. Import `badges` and `forms` by file path.

## Testing

- vitest enforces a 70% line coverage floor (`vite.config.ts`). A drop below the
  floor fails the build.
- Match colon-action endpoints (`:publish`, `:archive`) by concrete URL in tests.
  `path-to-regexp` treats the second colon as a param.
- MSW handler paths must stay `*`-prefixed so they match any API base.
- Use `renderWithProviders` when a component reads data or auth through the stack.
  Use `renderWithAuth` for pure chrome. Do not build a bespoke provider tree per
  test.
- The dev proxy proxies only same-origin SPA routes. It does not proxy the OAuth
  AS or agent endpoints; the MCP Inspector hits `:8000` directly.
  `vite.dev-proxy.test.ts` locks this.
