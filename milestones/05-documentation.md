# Milestone 05 — Documentation

## Objective

Someone returning after months, or after a dead drive, can operate and restore without chat history.

## Dependencies

Requires Milestones 01–04 (documents their actual behavior).

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`README.md`, `RESTORE.md`.

## Required work

- README: what it is, prerequisites, `make up`/`make down`/`make help`, URL, creating a job, modes, pre-command example (`docker exec <pg> pg_dumpall`), the safety rules, configuration (`.env`), security note (localhost only, root access), known limitations.
- RESTORE.md: short steps for restoring after a drive failure, for mirror and snapshot layouts, using plain `rsync` on the host (works without this app).

## Completion criteria

- [x] README covers purpose, prerequisites, start, stop, usage and configuration
- [x] RESTORE.md explains how to copy a backup back

## Verification

Read both files against the running app: every command and path they mention exists.
