# Milestone 01 — Foundation

## Objective

A runnable Docker Compose app with a web UI, a Makefile interface and persistent state.

## Dependencies

None.

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`Makefile`, `compose.yaml`, `Dockerfile`, `.env.example`, `.gitignore`, `app/`, `tests/`, a minimal `README.md`.

## Required work

- Python + Flask app served by waitress, one container, `rsync` installed in the image.
- Host `/` bind-mounted at `/host` with `rslave` propagation, so `/mnt/bulk` (and any later mount) is visible inside.
- The UI binds to `127.0.0.1:8095` by default (`BIND_ADDRESS`/`PORT` in `.env`). POSTs with a foreign `Origin` and requests with an unexpected `Host` are rejected (the app can run shell commands as root, so CSRF and DNS rebinding matter).
- SQLite database at `./data/backupmanager.db` (bind mount, git-ignored).
- The dashboard lists physical drives (deduplicated by disk) with total, used and free space.
- `make up` fails clearly when Docker is missing and waits until the UI responds.

## Completion criteria

- [x] `make up` builds and starts the container; the UI answers on http://127.0.0.1:8095
- [x] `make down`, `make help`, `make logs`, `make status`, `make test` exist
- [x] Dashboard shows free space for each physical drive
- [x] SQLite state persists in `./data` across `make down` / `make up`

## Verification

`make up`, then `curl` the dashboard; `make down && make up` and confirm the DB file still exists.
