# Runbook: rollback

Rollback restores the previously deployed version. It is **image-only but
complete and git-consistent**: it re-pulls the previous images and pins the git
checkout to the matching SHA. It does **not** revert the database, which is why
the migration discipline in `migration.md` matters.

## Automatic rollback

`scripts/deploy.sh` rolls back on its own when the post-start health gate
(phase 12) fails. Given the previous SHA (read from `/opt/wren/.deployed-sha`,
recorded at the end of the last successful deploy) it:

1. Auto-derives **all** first-party images (`ghcr.io/<owner>/wren/*`) from
   `docker compose config` (never a hard-coded list, so a new service is picked
   up automatically) and re-pulls each at `:sha-<prev>`.
2. Pins the checkout: `git reset --hard <prev>` (so the compose file and tunnel
   template match the rolled-back code).
3. Re-renders the tunnel config and brings the stack back up on `:sha-<prev>`.

If no previous SHA is recorded (e.g. the very first deploy), automatic rollback
cannot proceed and the deploy exits non-zero with that message.

## Prerequisites

- **`:sha-<prev>` images exist in GHCR.** CD dual-tags every build `:latest` +
  `:sha-<github.sha>`, so the previous SHA's images are pullable. Rollback fails
  if they were pruned from the registry.
- **`/opt/wren/.deployed-sha` is present.** Written on each successful deploy;
  it is the rollback target.
- **The rollback is expand/contract-safe.** See limits below.

## Manual rollback

To roll back deliberately (not just on a failed health gate), re-deploy the known
good commit so its `:latest` images and checkout are restored:

```
DEPLOY_SHA=<good-sha> just deploy <server-ip>
```

Ensure `origin/main` points at the good commit (or roll `main` back first), since
phase 6 syncs to `origin/main`. Preview first with `just deploy-plan <server-ip>`.

## Limits

- **Image + git only, never the database.** A rollback across a **destructive**
  migration (one the previous image cannot run against) is unsafe: the old image
  will fault on the new schema. Only additive/backward-compatible (expand/
  contract) migrations keep image-only rollback safe: see `migration.md`.
- **Not zero-downtime.** Recreating containers causes a brief gap, accepted at
  this scale.
- **Registry retention.** If `:sha-<prev>` was pruned from GHCR, restore from a
  build or re-tag before rolling back.
