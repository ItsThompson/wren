# docs-site

Customer-facing Wren documentation, served at `docs.usewren.com`. A
[VitePress](https://vitepress.dev) static site built in CI and served by nginx,
mirroring the `frontend` container pattern (SSG build then nginx static serve).

This is a separate package from the top-level `docs/` directory, which holds
internal engineering docs.

## Develop

```sh
npm install        # install deps (generates package-lock.json on first run)
npm run dev        # local dev server with hot reload
npm run build      # static build to .vitepress/dist (fails on dead links)
npm run preview    # preview the built site
```

Markdown content lives under `docs/`; site configuration (title, nav, sidebar,
search, base URL) lives in `.vitepress/config.ts`.

## Container

`Dockerfile` is a multi-stage build: `node:22-alpine` runs the VitePress build,
then `nginx:1.27-alpine` serves the static output with a history fallback for
deep links and a local `/healthz` endpoint for the Compose health gate. See
`nginx.conf`.
