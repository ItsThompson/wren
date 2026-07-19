# Runbook: database migrations

How schema changes reach production, and the discipline that keeps an
image-only rollback (see `rollback.md`) safe.

## Migrations are an explicit, pre-traffic deploy step

Alembic migrations run as a distinct step **before** the app containers start,
never at app startup. `scripts/deploy.sh` does, pre-traffic (deploy step 3 of 6):

```
docker compose up -d postgres      # bring the DB up, wait until healthy
docker compose run --rm backend alembic upgrade head
```

If `alembic upgrade head` fails, the deploy aborts **before** any app container
serves traffic. A migration failure is therefore a clean, pre-traffic failure,
not an app crash-loop. There is no `seed-admin` or other DB bootstrap: migrations
are the only thing that shapes the schema (humans self-register; there is no
operator role).

Locally the same step is `just migrate`; author a new migration with
`just migrate-new "message"`.

## Expand/contract discipline

Rollback restores a previous **image** (`:sha-<prev>`) and pins the git checkout
to that SHA, but it does **not** revert the database. Old code must therefore be
able to run against the new schema. Keep every normal deploy additive and
backward-compatible:

- **Expand:** add tables, add nullable columns, add new columns with defaults,
  add indexes. Old code ignores what it does not know about, so a rollback to the
  previous image keeps working against the expanded schema.
- **Avoid in a normal deploy:** dropping or renaming a column/table still read by
  the currently-running image, tightening a constraint the old code can violate,
  or any change that makes the previous image fail against the new schema.

A rename is an expand/contract sequence spread across **separate deploys**:

1. Deploy A: add the new column, write to both old and new, backfill.
2. Deploy B (only once A is confirmed stable): stop reading the old column.
3. Deploy C: drop the old column.

Each step is independently rollback-safe because the running image always
understands the schema it sees.

## Destructive / irreversible changes

Genuinely destructive changes (dropping data, non-reversible transforms) are
operator-discretion and are done as a **deliberate, separate migration**, run
with care and outside the normal additive flow. Once a destructive migration has
run, an image-only rollback across it is no longer safe: see the limits section
in `rollback.md`. There is no automated change-management ritual at this scale;
the safeguard is this discipline.

## Backups

Off-host backups are deferred post-P0 (accepted risk): single-VPS disk failure is
total data loss until nightly `pg_dump` to object storage lands. Do not rely on a
backup existing when planning a destructive migration.
