# Milestone 08 — Path assistance (v1.2.0)

## Objective

Let a user who doesn't know absolute paths pick the source and destination: type `~/...` or symlinked paths, see immediately what a path means, or browse for it.

## Dependencies

Requires Milestone 07 (job form with Check button).

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`compose.yaml`, `app/disks.py`, `app/engine.py`, `app/web.py`, `app/templates/job_form.html`, `tests/`, `README.md`.

## Required work

- `HOST_HOME` (the `$HOME` of whoever runs `make up`) is passed to the container. `~` and `~/x` expand to it.
- Symlinks are resolved with host semantics: an absolute target is relative to the host root, not the container root. The resolved real path is validated and stored. Replaces the old "symlinks are refused" rule.
- At run time, refuse if a stored path no longer resolves to itself.
- `GET /api/path?p=` returns the real path, whether it exists, its drive and mount, and for a folder whether it is empty or has the backup marker.
- `GET /api/browse?p=` returns subfolders (hidden folders excluded, capped), the parent, the drive, and shortcuts (Home, each mounted drive).
- Form: debounced live info under both fields, a same-drive warning, and a Browse… picker (vanilla JS, no new dependency).

## Completion criteria

- [x] `~` and symlinked paths (e.g. `~/Bulk` → `/mnt/bulk`) are accepted and stored as the real path
- [x] Under the source and destination fields, live feedback shows the real path, its drive and whether it is usable
- [x] A Browse… button opens a folder picker with shortcuts to Home and each drive
- [x] A run is refused if a saved path now resolves somewhere else (e.g. a folder was replaced by a symlink)

## Verification

`make test` (resolution and `~`). Live: the API on `~/Bulk/Public/projects`, and a form check with `~` paths.
