# scripts/ops/

Host-side ops scripts that run **on the VPS** and operate against the running stack directly (e.g. `docker exec` into the postgres container).

These are **not** Docker-Context scripts and are not run from CI. An operator SSH's into the VPS and runs them.

## How they reach the box

The box holds no repo checkout. Each successful deploy (`scripts/deploy.sh` step 6) syncs this directory to `/opt/wren/scripts/` on the VPS via a clean-replace `tar` over SSH: the directory is wiped and re-extracted, so removed scripts don't linger and the scripts always match the running deploy.

## Usage

```sh
ssh deploy@<vps-ip>

# Run any script from the synced directory:
/opt/wren/scripts/<script>.sh [args]
```

## Convention

- Scripts here call `docker exec` against containers on the VPS directly.
- CLI-side scripts that drive the Docker Context from a checkout (like `deploy.sh`) stay in `scripts/`, not here.
- Every script should have a `WREN_PG_CONTAINER` env override (default `wren-postgres-1`) so it works without changes on a differently-named container.
- Add a test in `scripts/tests/` (the `run_all.sh` harness auto-discovers `*_test.sh`).
