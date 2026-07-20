# wren MCP server

The wren MCP server is the AI-agent front door. It exposes roadmap authoring and
study tools over the Model Context Protocol (MCP), so an agent can create,
publish, and study roadmaps.

## Purpose

- The server is an OAuth 2.1 Resource Server (RS). It verifies each agent's bearer
  access token against the backend Authorization Server, then forwards the
  resolved user identity to the backend internal app (`:8001`).
- It is a thin dispatcher. Each tool body is one authenticated call to the
  backend. The roadmap rules live in the backend service layer, not here.
- The tunnel reaches it at `mcp.usewren.com`, which exposes only the Protected
  Resource Metadata document and the `/mcp` transport.

## Architecture

- The RS imports no backend code. It ships as a separate image.
- Wire truths it shares with the backend (the internal-boundary header names, the
  OAuth scopes, the tool schema shapes) are re-declared here and kept in sync by
  contract tests, not by import.
- The bearer boundary guards the `/mcp` prefix. `require_scope` is the only way a
  tool obtains its `user_id`, so a tool cannot skip authorization.
- The agent bearer token is never forwarded downstream. Only the resolved
  `user_id` and the shared internal token cross the internal hop (the
  confused-deputy defense).

See `../docs/mcp.md` for the transport, the bearer boundary, the full tool
catalog, and the internal-hop contract.

## Setup and run

All recipes run from the repo root and change into `mcp/`.

| Command | Purpose |
|---------|---------|
| `just setup-mcp` | Install dependencies into `mcp/.venv` from `uv.lock` |
| `just dev-mcp` | Run the RS (`:9000`) with autoreload; the MCP Inspector attaches here |
| `just test-mcp` | Run the test suite with coverage |
| `just lint-mcp` | Ruff check, format check, and mypy |
| `just fmt-mcp` | Format and autofix |
| `just sync-skill` | Re-sync the backend-bundled `SKILL.md` after editing the root copy |

## Configuration

Copy `.env.example` to `.env` at the repo root and fill in the MCP values.
`.env.example` is the canonical annotated list of every environment variable. Do
not duplicate it here.

## Further reading

- MCP transport, tools, and boundary contract: `../docs/mcp.md`
- Token model and OAuth: `../docs/auth.md`
- Cross-package duplication and its drift gate: `../docs/infra-duplication.md`
- Metrics and alerts: `../docs/monitoring.md`
