# Milestone 02 — Jobs and drive safety

## Objective

Create, edit and delete backup jobs, and refuse any job whose source and destination share a physical disk.

## Dependencies

Requires Milestone 01 (app, DB, `/host` mount).

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`app/`, `tests/`.

## Required work

- Job fields: name, source (host path), destination (host path), mode (`mirror` | `snapshot`), keep_daily (default 7), keep_weekly (default 4), daily run time (default 03:00), optional pre-backup command, enabled flag.
- Paths must be absolute host paths without symlink components. The source must exist. The destination may not exist yet.
- Physical disk resolution: `st_dev` → `/sys/dev/block/MAJ:MIN` → the partition's parent disk, following `slaves/` for LVM/dm. If the disk can't be determined, refuse (fail safe).
- Refuse when the disks overlap, or when one path is inside the other.
- Store the mount point of the source and of the destination when the job is saved (used by run-time checks in Milestone 03).

## Completion criteria

- [x] Jobs can be created, edited and deleted in the UI
- [x] A job whose source and destination are on the same physical disk is refused
- [x] A destination inside the source (or the reverse) is refused
- [x] Unit tests cover the path and disk checks

## Verification

`make test`. In the UI, try `/home/...` → `/home/...` (refused) and `/home/...` → `/mnt/bulk/...` (accepted).
