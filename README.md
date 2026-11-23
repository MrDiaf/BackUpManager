# Backup Manager

A small web app (Docker Compose + rsync) that copies chosen folders from one physical
drive to another every day. It protects against **one drive dying**. If a drive fails,
you replace it or reinstall the OS, copy the folders back from the surviving drive
(see [RESTORE.md](RESTORE.md)), and carry on.

It is not a versioned off-site backup. Both drives are in the same machine, so theft,
fire, or a power surge that kills both drives are not covered.

## What it does

- **Jobs**: each job copies one *source* folder to one *destination* folder.
- **Different drive enforced**: a job is refused if the source and destination are on the
  same physical disk, which is detected through `/sys`, including partitions and LVM.
  The check runs when you save the job and again before every run.
- **Never writes to the wrong disk**: before each run it checks that the source and
  destination are still on the filesystems they were on when the job was saved. If
  `/mnt/bulk` is not mounted, `/mnt/bulk/...` is just a folder on the OS drive, so the run
  is refused.
- **Never wipes what it didn't create**: the destination must be empty or new on the first
  run. A `.backupmanager` marker file is then written, and later runs refuse a destination
  that lacks it. An empty source is refused too, so a missing drive can't mirror
  "nothing" over a good backup.
- **Two modes per job**:
  - *Mirror*: one exact copy (`rsync -aHAX --delete`). Files deleted from the source are
    deleted from the backup at the next run.
  - *Dated daily copies*: a `YYYY-MM-DD_HHMMSS` folder per run, made with
    `rsync --link-dest`, so unchanged files are hard links and cost no extra space. Keeps
    the newest copy of each of the last *N* days (default 7) plus the newest of each of the
    last *M* weeks (default 4). `latest` points at the newest copy.
- **Schedule**: daily at a per-job time (default 03:00, host time zone), plus a **Run now**
  button. If the machine was off at the scheduled time, the job runs as soon as the app
  starts again. Jobs run one at a time.
- **Check (dry run)** button per job: runs every safety check and `rsync --dry-run`, and
  reports how many files a backup would copy and delete. It writes nothing: the
  pre-backup command is skipped, and no marker, snapshot or pruning happens. Checks show
  in the job's run history but don't count as the last backup on the dashboard.
- **Pre-backup command** (optional, per job), for example a database dump. If it exits
  non-zero, the backup is not run and is marked failed.
- **Dashboard**: status (OK / failed / running), last run, duration, size, next run, logs
  for each run, and free space on every drive.

## Prerequisites

- Linux with Docker and Docker Compose v2 (`docker compose`), and your user in the
  `docker` group.
- `make`.
- At least two physical drives mounted on the host. Mount data drives through `/etc/fstab`
  (`nofail` is fine: the app refuses to run when the drive is missing).

## Start, stop, use

```bash
make up      # build and start; prints the URL
make down    # stop (jobs, history and backups are kept)
make help    # all commands
```

Open **http://127.0.0.1:8095** on this machine, or **http://<this-machine's-IP>:8095**
from any device on your local network (`make up` prints the address). Log in with any
username and the password shown by `make password`.

1. Click **+ New job**.
2. Enter the **source** and **destination** as normal host paths, for example
   `/home/ronny` → `/mnt/bulk/backups/home`, or `/mnt/bulk/photos` →
   `/home/ronny/backups/photos` for the other direction. The form lists your drives, and an
   error explains why a pair is refused.
3. Pick *Mirror* or *Dated daily copies* and set the time.
4. Click **Check (dry run)** beside Save to confirm the drives and paths are right and to
   see what the first backup would copy. Nothing is saved or written. Then click **Save**.
   The job page and the dashboard have a **Check** button too.
5. Click **Run now** for the first real backup, then watch the dashboard (it refreshes
   every 15 s). Click a run's time to see its rsync log.

Other commands: `make password` (UI password), `make logs` (app logs), `make status`, `make restart`, `make test` (unit
tests, run inside the image).

### Databases in containers (Postgres)

Copying the files of a running database can give a broken copy. Dump it first with a
pre-backup command. The command runs with `sh -c` inside the source folder, as root, and
the `docker` CLI is available:

```sh
docker exec my-postgres pg_dumpall -U postgres > pg_dumpall.sql
```

The dump lands in the source folder and is copied with everything else. Restore it with
`psql -U postgres -f pg_dumpall.sql`.

Inside the command, host path `/x` is `/host/x`. `$SOURCE` and `$DEST` hold those
container paths. The command times out after 1 hour.

## Configuration

Optional. Copy `.env.example` to `.env`:

| Variable       | Default   | Meaning |
|----------------|-----------|---------|
| `BIND_ADDRESS` | `0.0.0.0` | Host address the UI listens on. `127.0.0.1` = this machine only |
| `PORT`         | `8095`    | Host port of the UI |
| `UI_PASSWORD`  | (random)  | UI password. If empty, a random one is generated on first start into `data/ui-password` |

State lives in `./data/` (SQLite database `backupmanager.db` plus run logs in `logs/`).
It is git-ignored and kept by `make down`. Its files are owned by root because the
container runs as root.

## Security

The container runs as **root** with the whole host filesystem mounted read-write at
`/host` and access to the Docker socket. It needs that to read every file and to run
pre-backup commands. Anyone who can use the UI can run commands as root on this machine.
So:

- Every page requires the password (HTTP Basic auth, any username). Keep the generated
  one or set a long `UI_PASSWORD`.
- The UI is reachable from your **local network**. Don't forward port 8095 on your router
  or otherwise expose it to the internet.
- It is plain HTTP: the password travels unencrypted, so someone who can sniff your LAN
  traffic (for example on shared Wi-Fi) could read it. For this machine only, set
  `BIND_ADDRESS=127.0.0.1` in `.env` and use an SSH tunnel from elsewhere
  (`ssh -L 8095:127.0.0.1:8095 thishost`).
- Cross-site form posts (CSRF) are rejected, so another web page can't use your logged-in
  browser to drive the UI.

## Known limitations

- **Two runs on the same day** in dated mode: only the newest copy of that day is kept.
- **Symlinked paths**: source and destination must be real paths, not paths through a
  symlink, because absolute symlinks resolve differently inside the container.
- **No notifications**: failures show only on the dashboard. Look at it now and then.
- **Back up the app's own state** if you care about job definitions: add a job for this
  project folder, or just re-create the jobs after a reinstall. Backups on disk don't
  depend on the app (see [RESTORE.md](RESTORE.md)).
- Moving a destination to a different drive requires editing and re-saving the job. A
  run refuses if a destination's drive changed since the job was saved.

## Files

- `app/`: Flask app (`web.py` UI, `engine.py` runs/schedule/rsync, `disks.py` drive
  detection, `db.py` SQLite)
- `tests/`: unit tests (`make test`)
- `PLAN.md`, `milestones/`: implementation plan and status
