# Progress

Purpose: a Docker Compose backup manager that uses rsync to copy folders between two
physical drives (NVMe `/` and WD HDD `/mnt/bulk`). It protects against one drive dying.

Order: 01 → 02 → 03 → 04 → 05. Each milestone depends on the previous one.

## Milestone 01 — Foundation
- [x] `make up` builds and starts the container; the UI answers on http://127.0.0.1:8095
- [x] `make down`, `make help`, `make logs`, `make status`, `make test` exist
- [x] Dashboard shows free space for each physical drive
- [x] SQLite state persists in `./data` across `make down` / `make up`

## Milestone 02 — Jobs and drive safety
- [x] Jobs can be created, edited and deleted in the UI
- [x] A job whose source and destination are on the same physical disk is refused
- [x] A destination inside the source (or the reverse) is refused
- [x] Unit tests cover the path and disk checks

## Milestone 03 — Backup engine
- [x] Mirror mode runs `rsync --delete` and keeps the destination marker
- [x] Snapshot mode makes dated copies with `--link-dest` and prunes by keep-daily/keep-weekly
- [x] A run is refused if a drive is unmounted, the disks match, the source is empty, or the destination marker is missing
- [x] The optional pre-backup command runs first, and a failing command fails the run
- [x] "Run now" works; each run records status, duration, size and a log

## Milestone 04 — Schedule and monitoring
- [x] Each job runs daily at its time (default 03:00), and a missed run starts on the next startup
- [x] The dashboard shows last run, status, duration, size and next run for each job
- [x] A run left as "running" by a restart is marked failed

## Milestone 05 — Documentation
- [x] README covers purpose, prerequisites, start, stop, usage and configuration
- [x] RESTORE.md explains how to copy a backup back

## Milestone 06 — Local network access
- [x] The UI is reachable from other machines on the LAN at http://<host-ip>:8095
- [x] Every page except `/health` requires the password (401 without it)
- [x] A random password is generated on first start unless `UI_PASSWORD` is set; `make password` shows it
- [x] Cross-site POSTs are still refused, also with valid credentials
