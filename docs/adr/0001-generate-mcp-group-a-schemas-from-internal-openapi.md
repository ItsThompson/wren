# Generate the MCP Group-A schemas from the internal OpenAPI

- Status: accepted
- Deciders: repository owner
- Date: 2026-07-20

## Context and Problem Statement

The MCP server ships as a separate image that carries no backend domain code, so
it re-declares about 50 Pydantic types that mirror the backend authoring and read
projections: roughly 46 field-identical Group-A types (the ones this decision
generates), plus a handful of lean write results and one MCP-only wrapper that
stay hand-authored. A cross-package test (`contract/tests/test_schema_mirror.py`)
holds the mirror equal, so drift is caught in CI rather than prevented. Adding an
agent-facing endpoint costs about ten edits across three packages, and the
hand-mirrored schemas are the largest part of that cost. We need a way to remove
the schema duplication without pulling backend domain code into the MCP image.

## Decision Drivers

- Remove the largest duplication cost in adding an agent-facing endpoint.
- Make schema drift structurally impossible instead of CI-caught.
- Keep the MCP image free of any backend domain dependency (it may import
  `wren-common` infra, never `wren`).
- Preserve the frozen agent tool contract byte-for-byte on fields, types, enums,
  `required`, and discriminators.
- Keep the security-critical internal hop hand-authored and reviewable.

## Considered Options

1. Generate the Group-A schemas only from the internal app's OpenAPI document;
   keep `mcp/client.py` hand-authored.
2. Generate the Group-A schemas and the client methods from the internal OpenAPI.
3. Keep the schemas hand-mirrored and rely on the contract-drift test.

## Decision Outcome

Chosen option: "Generate the Group-A schemas only", because it removes the
schema duplication and its drift machinery while leaving the security boundary
(`mcp/client.py`) hand-authored, honoring the no-backend-domain-dependency
constraint.

The internal app's OpenAPI document is the source of truth. Wren already treats a
FastAPI surface as the source for the frontend client (`just codegen` exports the
external app's OpenAPI and runs `openapi-typescript`, drift-gated in CI). This
decision extends the same pattern to the MCP Group-A schemas, sourced from the
internal app's OpenAPI, which is exactly the surface the MCP tools consume.

Generation runs in the uv workspace off a committed internal-OpenAPI artifact
that a backend-member step exports. `datamodel-code-generator` is an MCP **dev**
dependency, never a runtime one. CI regenerates and runs `git diff --exit-code`,
mirroring the frontend `codegen-drift` job. The MCP image only copies the
committed generated files; it never runs codegen and never imports `wren`.

The generator emits a Pydantic class for every component in the internal OpenAPI,
which is a superset of Group A and includes the full `Roadmap` (which carries
`visibility: Visibility`). We therefore restrict the generation input to the
Group-A component set (a test-guarded allowlist) before generation, so the
non-Group-A domain types are never emitted. We then apply two deterministic
transforms: drop the `visibility` property from the authoring input, and rename
the generated `RoadmapInput` to `RoadmapDraftInput` (the name the frozen contract
and `tools_write` use). Because Group A no longer references `Visibility`, that
enum becomes unreferenced and absent. The agent field contract stays byte
identical.

### Positive Consequences

- Schema drift for Group A becomes structurally impossible.
- The Group-A equality machinery in `test_schema_mirror.py` retires; the header,
  scope, and Group-B fields-subset tests remain the enforcement for the parts
  that stay hand-authored.
- Adding an agent-facing endpoint no longer requires hand-editing the MCP
  schemas for Group-A types.

### Negative Consequences

- Generated type names and per-field descriptions differ cosmetically from the
  hand-authored ones, forcing a one-time deliberate refresh of the frozen tool
  snapshot (`mcp/tests/snapshots/tools_schema.json`). A structural-equality guard
  asserts only `title` and `description` changed, so no agent-facing field,
  type, enum, `required`, or discriminator can change unnoticed.
- The build gains a generation step and a new committed artifact
  (`mcp/internal-openapi.json`) plus a CI drift gate to maintain.
- A Group-A allowlist must be maintained; a test asserts it equals the generated
  module's declared types, so over- or under-inclusion fails CI.

## Pros and Cons of the Options

### Option 1: generate schemas only

- Good, because it removes the schema duplication and its drift machinery.
- Good, because it leaves the security-critical `_request` hop hand-authored and
  reviewable.
- Good, because it keeps the MCP image free of backend domain code.
- Bad, because it introduces a generation step, a committed artifact, and a
  deliberate tool-snapshot refresh.

### Option 2: generate schemas and the client

- Good, because it would also remove the client-method duplication.
- Bad, because `mcp/client.py`'s `_request` helper owns the confused-deputy
  defense (it sets `X-User-ID` and `INTERNAL_API_TOKEN` last and never forwards
  the agent bearer); generating it risks the security boundary for little gain.
- Bad, because the named methods carry HTTP path and verb knowledge, not
  field-level schema duplication, so they sit outside the drift the schema mirror
  guards.

### Option 3: keep the schemas hand-mirrored

- Good, because it needs no new build wiring.
- Bad, because it keeps the largest duplication cost and leaves drift as a
  CI-caught failure rather than a structural impossibility.

## Links

- Ticket: Improve Wren external/internal API pattern and reduce cross-surface duplication.
- `docs/packaging.md`: the uv workspace, per-member images, and the backend/MCP boundary.
- `docs/mcp.md`: the MCP transport, tool catalog, and the internal-hop contract.
