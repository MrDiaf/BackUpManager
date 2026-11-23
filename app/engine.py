"""Runs backups: one worker thread executes queued jobs one at a time, and a
scheduler thread queues each enabled job once a day at its configured time."""
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta

import db
import disks
from disks import PathError

MARKER = ".backupmanager"
INCOMPLETE = ".incomplete"
SNAPSHOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
SNAPSHOT_FMT = "%Y-%m-%d_%H%M%S"
RSYNC_BASE = ["rsync", "-aHAX", "--numeric-ids", "--delete", "--stats", "--itemize-changes"]
PRE_COMMAND_TIMEOUT = 3600
SCHEDULER_INTERVAL = 30


class RunRefused(Exception):
    """A safety check failed; nothing was written."""


class RunFailed(Exception):
    pass


# --- pure helpers (unit tested) ---------------------------------------------------

def next_occurrence(run_time, after):
    """Next local datetime strictly after `after` at HH:MM."""
    h, m = (int(x) for x in run_time.split(":"))
    candidate = after.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


def snapshots_to_keep(names, keep_daily, keep_weekly):
    """Newest snapshot of each of the last `keep_daily` days that have snapshots,
    plus the newest of each of the last `keep_weekly` ISO weeks. The newest
    snapshot is always kept."""
    newest_first = sorted((n for n in names if SNAPSHOT_RE.match(n)), reverse=True)
    keep, days, weeks = set(newest_first[:1]), [], []
    for name in newest_first:
        d = datetime.strptime(name, SNAPSHOT_FMT).date()
        if d not in days:
            days.append(d)
            if len(days) <= keep_daily:
                keep.add(name)
        week = d.isocalendar()[:2]
        if week not in weeks:
            weeks.append(week)
            if len(weeks) <= keep_weekly:
                keep.add(name)
    return keep


def _stat(rsync_output, label):
    m = re.search(label + r": ([\d,.]+)", rsync_output)
    return int(re.sub(r"[,.]", "", m.group(1))) if m else None


def parse_total_size(rsync_output):
    return _stat(rsync_output, "Total file size")


def human_size(n):
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def dry_run_summary(rsync_output):
    files = _stat(rsync_output, "Number of regular files transferred") or 0
    sent = _stat(rsync_output, "Total transferred file size") or 0
    deleted = _stat(rsync_output, "Number of deleted files") or 0
    return (f"Check OK. A backup now would copy {files} file(s) ({human_size(sent)}) "
            f"and delete {deleted} file(s) from the backup. Nothing was written.")


# --- safety checks --------------------------------------------------------------

def check_before_run(job):
    """Re-check everything at run time: drives can be unplugged or fail to mount."""
    source, dest = job["source"], job["dest"]
    csrc, cdst = disks.to_container(source), disks.to_container(dest)

    for label, cpath, expected in (("Source", csrc, job["src_mount"]), ("Destination", cdst, job["dst_mount"])):
        existing = disks.nearest_existing(cpath)
        actual = disks.to_host(disks.mount_point(existing))
        if actual != expected:
            raise RunRefused(
                f"{label} drive is not mounted: {disks.to_host(cpath)} should be on the filesystem "
                f"mounted at {expected}, but it is now on {actual}. Mount the drive and run again.")
    try:
        placement = disks.check_pair(source, dest)
    except PathError as e:
        raise RunRefused(str(e))
    for label, saved, now in (("Source", source, placement.source), ("Destination", dest, placement.dest)):
        if saved != now:
            raise RunRefused(f"{label} {saved} now leads to {now} (a folder on the way became a symlink). "
                             "Edit and re-save the job if this is intended.")
    expected_dst = set(job["dst_disks"].split(","))
    if placement.dst_disks != expected_dst:
        raise RunRefused(
            f"Destination is now on drive {', '.join(sorted(placement.dst_disks))}, "
            f"but the job was saved for {', '.join(sorted(expected_dst))}. Edit and re-save the job if this is intended.")
    return csrc, cdst


def check_source_not_empty(csrc):
    with os.scandir(csrc) as it:
        if next(it, None) is None:
            raise RunRefused(f"Source {disks.to_host(csrc)} is empty. Refusing to back up nothing "
                             "(an unmounted or broken source would otherwise wipe the backup).")


def destination_is_new(cdst):
    """The destination must carry our marker, or be missing/empty (first run).
    Returns True for a first run. Only inspects; writes nothing."""
    if os.path.isfile(os.path.join(cdst, MARKER)):
        return False
    if os.path.isdir(cdst) and os.listdir(cdst):
        raise RunRefused(
            f"Destination {disks.to_host(cdst)} is not empty and was not created by this backup manager "
            f"(no {MARKER} file). Refusing to write into it. Choose an empty or new folder.")
    return True


def prepare_destination(cdst, job_id, log):
    if not destination_is_new(cdst):
        return
    marker = os.path.join(cdst, MARKER)
    os.makedirs(cdst, exist_ok=True)
    with open(marker, "w") as f:
        f.write(f"Backup destination of backupmanager job {job_id}, created {datetime.now().isoformat(timespec='seconds')}.\n"
                "Do not delete: without this file the backup manager refuses to write here.\n")
    log.write(f"First run: created {disks.to_host(marker)}\n")


# --- rsync ------------------------------------------------------------------------

def _rsync(args, log):
    log.write("$ " + " ".join(args) + "\n")
    log.flush()
    start = log.tell()
    code = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT).returncode
    log.flush()
    with open(log.name, errors="replace") as f:
        f.seek(start)
        output = f.read()
    if code == 24:
        log.write("Note: some files vanished while copying (rsync code 24). This is normal for live folders.\n")
    elif code != 0:
        raise RunFailed(f"rsync failed with exit code {code}. See the log.")
    return output


def run_mirror(csrc, cdst, log):
    return parse_total_size(_rsync(RSYNC_BASE + [f"--exclude=/{MARKER}", csrc.rstrip("/") + "/", cdst.rstrip("/") + "/"], log))


def run_snapshot(csrc, cdst, log, keep_daily, keep_weekly, now=None):
    now = now or datetime.now()
    snaps = sorted(n for n in os.listdir(cdst) if SNAPSHOT_RE.match(n))
    work = os.path.join(cdst, INCOMPLETE)  # reused if a previous run was interrupted
    args = RSYNC_BASE[:]
    if snaps:
        args.append(f"--link-dest={os.path.join(cdst, snaps[-1])}")
    size = parse_total_size(_rsync(args + [csrc.rstrip("/") + "/", work + "/"], log))

    name = now.strftime(SNAPSHOT_FMT)
    os.rename(work, os.path.join(cdst, name))
    tmp_link = os.path.join(cdst, ".latest.tmp")
    if os.path.lexists(tmp_link):
        os.remove(tmp_link)
    os.symlink(name, tmp_link)
    os.replace(tmp_link, os.path.join(cdst, "latest"))
    log.write(f"Snapshot {name} complete.\n")

    keep = snapshots_to_keep(snaps + [name], keep_daily, keep_weekly)
    for old in snaps:
        if old not in keep:
            log.write(f"Pruning old snapshot {old}\n")
            shutil.rmtree(os.path.join(cdst, old))
    return size


def run_pre_command(command, csrc, cdst, log):
    log.write(f"Running pre-backup command in {disks.to_host(csrc)}:\n$ {command}\n")
    log.flush()
    env = {**os.environ, "SOURCE": csrc, "DEST": cdst}
    try:
        code = subprocess.run(["sh", "-c", command], cwd=csrc, env=env, stdout=log,
                              stderr=subprocess.STDOUT, timeout=PRE_COMMAND_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        raise RunFailed(f"Pre-backup command timed out after {PRE_COMMAND_TIMEOUT // 60} minutes.")
    log.flush()
    if code != 0:
        raise RunFailed(f"Pre-backup command failed with exit code {code}. Backup not started.")


def dry_run(job, csrc, cdst, log):
    """rsync --dry-run with the real options. Writes nothing anywhere.
    Returns (total size, summary message)."""
    first_run = destination_is_new(cdst)
    if first_run:
        log.write(f"First run: {disks.to_host(cdst)} would be created with a {MARKER} marker.\n")
    with tempfile.TemporaryDirectory() as empty:
        args = RSYNC_BASE + ["--dry-run"]
        target = empty
        if job["mode"] == "mirror":
            args.append(f"--exclude=/{MARKER}")
            if not first_run:
                target = cdst
        elif not first_run:
            snaps = sorted(n for n in os.listdir(cdst) if SNAPSHOT_RE.match(n))
            if snaps:
                args.append(f"--link-dest={os.path.join(cdst, snaps[-1])}")
        output = _rsync(args + [csrc.rstrip("/") + "/", target + "/"], log)
    return parse_total_size(output), dry_run_summary(output)


# --- running a job ----------------------------------------------------------------

def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def check_job(job, log):
    """Dry run of a job (saved, or unsaved values from the form). Writes nothing.
    Raises RunRefused/RunFailed; returns (total size, summary message)."""
    csrc, cdst = check_before_run(job)
    log.write("CHECK (dry run): nothing will be written.\n")
    if job["pre_command"].strip():
        log.write(f"Pre-backup command would run first (skipped in a check):\n$ {job['pre_command']}\n")
    check_source_not_empty(csrc)
    return dry_run(job, csrc, cdst, log)


def backup(job, csrc, cdst, log):
    if job["pre_command"].strip():
        run_pre_command(job["pre_command"], csrc, cdst, log)
    check_source_not_empty(csrc)
    prepare_destination(cdst, job["id"], log)
    if job["mode"] == "mirror":
        size = run_mirror(csrc, cdst, log)
    else:
        size = run_snapshot(csrc, cdst, log, job["keep_daily"], job["keep_weekly"])
    return "ok", "Backup complete.", size


def execute_job(job_id, trigger):
    job = db.job(job_id)
    if job is None:  # deleted while queued
        return
    run_id = db.execute("INSERT INTO runs (job_id, trigger, started, status) VALUES (?, ?, ?, 'running')",
                        (job_id, trigger, now_iso()))
    status, message, size = "failed", "", None
    with open(db.log_path(run_id), "w") as log:
        log.write(f"[{now_iso()}] Job '{job['name']}' ({job['mode']}): {job['source']} -> {job['dest']}\n")
        try:
            if trigger == "check":
                size, message = check_job(job, log)
                status = "ok"
            else:
                csrc, cdst = check_before_run(job)
                status, message, size = backup(job, csrc, cdst, log)
        except (RunRefused, RunFailed) as e:
            message = str(e)
        except Exception as e:
            message = f"Unexpected error: {e}"
            log.write(traceback.format_exc())
        log.write(f"[{now_iso()}] {status.upper()}: {message}\n")
    db.execute("UPDATE runs SET ended = ?, status = ?, size_bytes = ?, message = ? WHERE id = ?",
               (now_iso(), status, size, message, run_id))


class Engine:
    def __init__(self):
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self.pending = set()   # job ids queued or running
        self.current = None    # (job id, trigger) running now

    def enqueue(self, job_id, trigger="manual"):
        with self._lock:
            if job_id in self.pending:
                return False
            self.pending.add(job_id)
        self._queue.put((job_id, trigger))
        return True

    def state(self, job_id):
        if self.current and self.current[0] == job_id:
            return "checking" if self.current[1] == "check" else "running"
        return "queued" if job_id in self.pending else None

    def _worker(self):
        while True:
            job_id, trigger = self._queue.get()
            self.current = (job_id, trigger)
            try:
                execute_job(job_id, trigger)
            except Exception:
                traceback.print_exc()
            finally:
                self.current = None
                with self._lock:
                    self.pending.discard(job_id)

    def schedule_tick(self, now=None):
        now = now or datetime.now()
        for job in db.jobs():
            if not job["enabled"]:
                continue
            if job["next_run"] is None or datetime.fromisoformat(job["next_run"]) <= now:
                if job["next_run"] is not None:  # a time set to None just gets a next_run
                    self.enqueue(job["id"], "schedule")
                db.execute("UPDATE jobs SET next_run = ? WHERE id = ?",
                           (next_occurrence(job["run_time"], now).isoformat(timespec="seconds"), job["id"]))

    def _scheduler(self):
        while True:
            try:
                self.schedule_tick()
            except Exception:
                traceback.print_exc()
            time.sleep(SCHEDULER_INTERVAL)

    def start(self):
        # Runs still "running" belong to a process that no longer exists.
        db.execute("UPDATE runs SET status = 'failed', ended = ?, message = 'Interrupted by a restart.' "
                   "WHERE status = 'running'", (now_iso(),))
        threading.Thread(target=self._worker, daemon=True, name="worker").start()
        threading.Thread(target=self._scheduler, daemon=True, name="scheduler").start()
