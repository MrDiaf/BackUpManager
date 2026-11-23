# Milestone 03 — Backup engine

## Objective

Run a job with rsync safely, from the "Run now" button, and record the result.

## Dependencies

Requires Milestone 02 (job model and disk checks).

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`app/`, `tests/`, `Dockerfile` (docker CLI for pre-commands).

## Required work

- One worker thread runs jobs one at a time from a queue. "Run now" enqueues a job. The same job is never queued twice.
- Run-time checks (all must pass, otherwise the run fails with a clear message):
  - The recorded source and destination mount points are still the mount points of those paths, and they are mounted.
  - The source and destination are still on different physical disks.
  - The source is not empty.
  - The destination either has the marker file `.backupmanager` or is empty or missing (first run, in which case the marker is created).
- Pre-backup command: `sh -c` with cwd = source and env `SOURCE`/`DEST` (container paths). The docker socket is available. Timeout 1h. A non-zero exit fails the run.
- Mirror: `rsync -aHAX --numeric-ids --delete --exclude=/.backupmanager src/ dst/`.
- Snapshot: rsync into `dst/.incomplete` with `--link-dest` pointing at the newest snapshot, then rename to `YYYY-MM-DD_HHMMSS` and update the `latest` symlink. Retention keeps the newest snapshot of each of the last `keep_daily` days plus the newest of each of the last `keep_weekly` ISO weeks. Prune only after a successful run.
- rsync exit 24 (vanished files) counts as OK.
- Each run records start, end, status (running/ok/failed), size (rsync "Total file size") and a log file at `data/logs/<run_id>.log`.

## Completion criteria

- [x] Mirror mode runs `rsync --delete` and keeps the destination marker
- [x] Snapshot mode makes dated copies with `--link-dest` and prunes by keep-daily/keep-weekly
- [x] A run is refused if a drive is unmounted, the disks match, the source is empty, or the destination marker is missing
- [x] The optional pre-backup command runs first, and a failing command fails the run
- [x] "Run now" works; each run records status, duration, size and a log

## Verification

`make test` (retention, stats parsing). A real run from a scratch folder on `/` to a test folder on `/mnt/bulk`, then clean up.
