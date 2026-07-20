# Cross-package infra duplication

The backend (`wren`) and the MCP resource server (`wren_mcp`) ship as separate images with **no shared code dependency**: the MCP image deliberately does not import backend code, and the backend does not import MCP code. Three small infra modules are therefore duplicated across the two packages rather than sourced from a shared library:

| Pair | What is shared | Where they diverge |
|------|----------------|--------------------|
| `backend/src/wren/core/logging.py` ↔ `mcp/src/wren_mcp/logging.py` | The whole module (structlog setup, processor chain, `get_logger`) | **Code-identical**; only the docstrings differ. |
| `backend/src/wren/core/metrics.py` ↔ `mcp/src/wren_mcp/metrics.py` | HTTP-metric families, the instrumentator wiring, `/metrics` exposition | The shared registry concatenated onto `/metrics`: backend imports `wren.core.observability.WREN_REGISTRY`, MCP imports `wren_mcp.tool_metrics.TOOL_METRICS_REGISTRY`. |
| `backend/src/wren/core/health.py` ↔ `mcp/src/wren_mcp/health.py` | `CheckResult`, the `ReadinessCheck` contract, the aggregator, `create_health_router` | The MCP copy adds exactly one MCP-only readiness check, `jwks_readiness_check` (plus `KeyProvider` import and `JWKS_CHECK_NAME`). |

## Decision: defer `wren-common`

A shared `wren-common` package that single-sources these three modules (logging verbatim, metrics/health cores with the variable part injected rather than imported) **is deliberately deferred**. Reasons:

- **Only two consumers.** The duplication is three small modules, and the variability is already expressed cleanly (a differing registry constant, one extra readiness check).
- **The MCP image carries no backend-code dependency by design.** A shared package reintroduces exactly the coupling that design avoids, or forces a third standalone package with its own build, versioning, and release cadence.
- **Single VPS, pre-prod.** The build/CI/versioning artifact for a shared package is not worth its cost at this scale.

**Revisit this decision when either trigger fires:**

1. A **third consumer** of any of these modules appears, or
2. The infra **actually diverges** beyond the current registry / JWKS-check variability (e.g. the logging processor chains stop being code-identical for a real reason, not an accidental edit).

At that point the clean shape is a `wren-common` package: `logging.py` verbatim, `metrics.py` with the registry passed in as a parameter, and `health.py` with the extra readiness checks passed in as a `Sequence[ReadinessCheck]`.

## Drift mitigation (while deferred)

Because the copies are maintained by hand, three guards keep them from silently drifting:

1. **Sync notes in the modules.** Each of the six modules above carries a short "kept in sync with the sibling copy" note at its divergence point, so an editor sees the duplication is a deliberate, visible choice.
2. **Drift checklist (manual, enforced at review).** When editing any of these modules, apply the same change to its sibling copy:
   - [ ] **A structlog processor added to one `logging.py` MUST be added to the other.** The two `logging.py` copies are code-identical; the processor chain (`_build_processors`) must stay identical across both. The request-id correlation currently uses ASGI middleware, **not** a structlog processor, so neither chain changed, but any future processor (e.g. binding a field onto every log line via the chain rather than `contextvars`) must land in both copies in the same change.
   - [ ] A change to the HTTP-metric families or instrumentator wiring in one `metrics.py` is mirrored in the other (only the concatenated registry is allowed to differ).
   - [ ] A change to the shared health core (`CheckResult`, the aggregator, `create_health_router`) in one `health.py` is mirrored in the other (only MCP's extra `jwks_readiness_check` is allowed to differ).
3. **Mechanical guard for the wire-truth constants.** Two duplicated wire truths are enforced automatically instead of by review, both in the `contract` project (run by the `contract-drift` CI job), the sole interpreter where both packages import together:
   - The internal-boundary header names (`USER_ID_HEADER` / `INTERNAL_TOKEN_HEADER`, declared in `backend/src/wren/core/identity.py` and re-declared in `mcp/src/wren_mcp/config.py`) plus the `X-Request-ID` correlation header, by `contract/tests/test_header_constants.py`.
   - The OAuth scope set (`SUPPORTED_SCOPES` and its members, declared in `backend/src/wren/oauth/config.py` and re-declared in `mcp/src/wren_mcp/config.py`), by `contract/tests/test_scope_constants.py`. A divergence would make the RS advertise a scope set in its PRM that the AS metadata does not support (or vice versa).
   - No duplicate constant test is added in either package; the contract assertion is the guard.
