# Milestone 04 — Schedule and monitoring

## Objective

Daily automatic runs and a dashboard that shows backup health at a glance.

## Dependencies

Requires Milestone 03 (run queue).

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`app/`, `tests/`, `compose.yaml` (host timezone).

## Required work

- Each job stores `next_run`. A scheduler thread checks every 30 s and enqueues enabled jobs whose `next_run` has passed, then moves `next_run` to the next occurrence of the job time. A `next_run` in the past at startup means a missed run, which runs immediately.
- The container uses the host timezone (`/etc/localtime` mounted read-only).
- On startup, runs still marked `running` become `failed` ("interrupted by restart").
- Dashboard per job: last run time, status (OK/failed/running), duration, size, next run, links to the job page and the log. The page auto-refreshes.

## Completion criteria

- [x] Each job runs daily at its time (default 03:00), and a missed run starts on the next startup
- [x] The dashboard shows last run, status, duration, size and next run for each job
- [x] A run left as "running" by a restart is marked failed

## Verification

`make test` (next-run calculation). Set a job time one minute ahead and watch it run.
