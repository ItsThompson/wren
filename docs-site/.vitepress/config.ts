import { defineConfig } from "vitepress";
import { fileURLToPath } from "node:url";

// Customer-facing docs for docs.usewren.com. Served at the domain root, so
// base is '/'. Markdown lives in docs/ (srcDir) while .vitepress/ stays at the
// package root; the build emits static output to .vitepress/dist.
export default defineConfig({
  title: "Wren",
  description:
    "Wren documentation: connect an agent and follow learning roadmaps.",
  base: "/",
  srcDir: "docs",

  // Light-only, matching the app (design-language.md §9 defers dark mode).
  // Removes the appearance toggle from the navbar entirely.
  appearance: false,

  // Clean URLs (/getting-started, no .html) match a modern docs site; nginx
  // resolves them on deep links via a $uri.html probe with an index.html
  // history fallback (see nginx.conf, US-DOCS-01).
  cleanUrls: true,

  // Dead links fail the build so broken internal links or missing pages cannot
  // ship (US-DOCS-04). This is the VitePress default; set explicitly to make the
  // build gate intentional.
  ignoreDeadLinks: false,

  // Light Shiki theme only: the app is light-only, so code blocks must not carry
  // a dark syntax palette.
  markdown: {
    theme: "github-light",
  },

  // The custom theme imports shared/theme/*.css from the repo root (one level
  // above this package). Allow the dev server to read it, and pin the shared
  // fonts.css bare `@fontsource-variable/...` url() specifiers to this package's
  // own node_modules (there is no repo-root node_modules), mirroring the
  // frontend's Vite config so the woff2 bundle from the single shared file.
  vite: {
    server: {
      fs: {
        allow: [fileURLToPath(new URL("../../", import.meta.url))],
      },
    },
    resolve: {
      alias: {
        "@fontsource-variable": fileURLToPath(
          new URL("../node_modules/@fontsource-variable", import.meta.url),
        ),
      },
    },
  },

  themeConfig: {
    nav: [{ text: "Getting Started", link: "/getting-started" }],
    sidebar: [
      {
        text: "Guide",
        items: [{ text: "Getting Started", link: "/getting-started" }],
      },
    ],

    // Surface the guide's H2/H3 sections in the right-hand "On this page"
    // outline so readers can jump within the guide (US-DOCS-03 navigation).
    outline: {
      level: [2, 3],
      label: "On this page",
    },

    search: {
      provider: "local",
    },
  },
});
