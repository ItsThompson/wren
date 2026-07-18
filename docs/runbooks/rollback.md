# Runbook: rollback

Rollback restores the previously deployed version. It is **CI-owned** and
restores the previous **images AND config**: CI checks out the previous
`.deployed-sha` in the runner and re-runs the deploy pinned to
`WREN_IMAGE_TAG=sha-<prev>`. It does **not** revert the database, which is why the
migration discipline in `migration.md` matters (migrations are forward-only).

## Automatic rollback

On a failed post-start health gate, `scripts/deploy.sh` exits non-zero WITHOUT any
internal re-deploy. CD (`cd.yml`) owns the rollback in a conditional step:

1. Reads the previous SHA via `./scripts/deploy.sh read-deployed-sha <ip>` (the
   value recorded in `/opt/wren/.deployed-sha` after the last healthy deploy).
2. Checks that SHA out in the runner (`git checkout <prev>`), so the compose
   files, `.env.prod`, and the rendered configs all match the rolled-back code.
3. Re-exports the config/secret env from that checkout and re-runs the deploy once
   with `WREN_IMAGE_TAG=sha-<prev>`, restoring the previous images AND config.

If no previous SHA is recorded (the very first deploy), `read-deployed-sha`
refuses (non-zero) and the workflow fails: there is nothing to roll back to.

## Prerequisites

- **`:sha-<prev>` images exist in GHCR.** CD dual-tags every build `:latest` +
  `:sha-<github.sha>`, so the previous SHA's images are pullable. Rollback fails
  if they were pruned from the registry.
- **`/opt/wren/.deployed-sha` is present.** Written on each successful deploy;
  it is the rollback target.
- **The rollback is expand/contract-safe.** See limits below.

## Manual rollback

To roll back deliberately (not just on a failed health gate), check out the known
good commit in your runner/checkout and re-deploy it pinned to its images:

```
git checkout <good-sha>
# export the config/secret env as in bring-up.md Phase E, then:
DEPLOY_SHA=<good-sha> WREN_IMAGE_TAG=sha-<good-sha> just deploy <server-ip>
```

The deploy reads the compose files and `.env.prod` from the checked-out commit, so
both images and config are restored. Preview first with `just deploy-plan
<server-ip>`.

## Limits

- **Images + config, never the database.** A rollback across a **destructive**
  migration (one the previous image cannot run against) is unsafe: the old image
  will fault on the new schema. Only additive/backward-compatible (expand/
  contract) migrations keep rollback safe: see `migration.md`.
- **Not zero-downtime.** Recreating containers causes a brief gap, accepted at
  this scale.
- **Registry retention.** If `:sha-<prev>` was pruned from GHCR, restore from a
  build or re-tag before rolling back.
