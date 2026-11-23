# Milestone 07 — Dry-run check (v1.1.0)

## Objective

Let the user confirm that a job works without changing anything on disk.

## Dependencies

Requires Milestones 03 (engine and safety checks) and 04 (dashboard).

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`app/engine.py`, `app/db.py`, `app/web.py`, `app/templates/`, `tests/`, `README.md`.

## Required work

- "Check" button beside "Save" on the new/edit job form: validates and dry-runs the values in the form without saving them, synchronously, and shows the result and log in the form. Not recorded as a run (an unsaved job has no id).
- "Check" button next to "Run now". It goes through the same queue, as a run with trigger `check`.
- A check runs the same checks as a real run, in the same order. The destination check only inspects: it never creates the marker.
- The pre-backup command is not run; the log says it would run.
- `rsync --dry-run` with the same options as the real run:
  - mirror into an existing destination: against the destination itself;
  - first run, or snapshot mode: against an empty temporary folder (snapshot mode with `--link-dest` at the newest snapshot).
- Result message: files that would be copied, bytes that would be transferred, files that would be deleted.
- The dashboard's last run and status ignore checks. The job page lists them with trigger `check`.

## Completion criteria

- [x] Each job has a "Check" button (dashboard and job page)
- [x] A check runs all run-time safety checks and `rsync --dry-run`, and reports what would be copied and deleted
- [x] A check writes nothing: no pre-command, no marker, no snapshot, no pruning
- [x] Checks appear in the job's run history but don't change the dashboard's last-backup status
- [x] The job form has a Check button beside Save that dry-runs the unsaved values and shows the result in the form

## Verification

`make test` (dry run writes nothing; foreign destination refused). A live check on a test job.
