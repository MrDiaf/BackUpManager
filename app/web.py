import hmac
import os
import re
import secrets
from datetime import datetime
from urllib.parse import urlsplit

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_file, url_for

import db
import disks
from disks import PathError
from engine import Engine, next_occurrence

app = Flask(__name__)
app.secret_key = os.urandom(32)  # only used for flash messages
engine = Engine()

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
PASSWORD_FILE = os.path.join(db.DATA_DIR, "ui-password")


def load_password():
    """UI_PASSWORD from the environment, else a random one generated once into data/."""
    password = os.environ.get("UI_PASSWORD", "").strip()
    if password:
        return password
    try:
        fd = os.open(PASSWORD_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(18) + "\n")
    except FileExistsError:
        pass
    with open(PASSWORD_FILE) as f:
        return f.read().strip()


# --- request guards -----------------------------------------------------------
# This UI runs shell commands as root and is reachable from the LAN, so every
# request needs the password, and a malicious web page must not be able to drive
# it through the user's browser (CSRF: browsers attach cached Basic credentials).

@app.before_request
def guard():
    if request.path == "/health":
        return
    auth = request.authorization
    given = (auth.password or "") if auth and auth.type == "basic" else ""
    if not hmac.compare_digest(given.encode(), app.config["PASSWORD"].encode()):
        return Response("Password required. Run 'make password' on the server to see it.\n", 401,
                        {"WWW-Authenticate": 'Basic realm="Backup Manager"'})
    if request.method == "POST":
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin and urlsplit(origin).netloc.lower() != request.host.lower():
            abort(403, "Cross-site request refused.")


@app.get("/health")
def health():
    return "ok"


# --- formatting -------------------------------------------------------------------

@app.template_filter("size")
def fmt_size(n):
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


@app.template_filter("when")
def fmt_when(iso):
    return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M") if iso else "—"


def duration(run):
    if not run:
        return "—"
    end = datetime.fromisoformat(run["ended"]) if run["ended"] else datetime.now()
    secs = int((end - datetime.fromisoformat(run["started"])).total_seconds())
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s" if m else f"{s}s"


app.jinja_env.globals["duration"] = duration


def job_status(job, last):
    live = engine.state(job["id"])
    if live:
        return live
    return last["status"] if last else "never"


# --- pages ------------------------------------------------------------------------

@app.get("/")
def dashboard():
    rows = []
    for job in db.jobs():
        last = db.last_run(job["id"])
        rows.append({"job": job, "last": last, "status": job_status(job, last)})
    return render_template("dashboard.html", rows=rows, drives=disks.drives())


def form_values(form):
    v = {
        "name": form.get("name", "").strip(),
        "source": form.get("source", "").strip(),
        "dest": form.get("dest", "").strip(),
        "mode": form.get("mode", "mirror"),
        "keep_daily": form.get("keep_daily", "7").strip(),
        "keep_weekly": form.get("keep_weekly", "4").strip(),
        "run_time": form.get("run_time", "03:00").strip(),
        "pre_command": form.get("pre_command", "").replace("\r\n", "\n").strip(),
        "enabled": 1 if form.get("enabled") else 0,
    }
    return v


def validate(v):
    """Returns the values to store, or raises PathError/ValueError with a message."""
    if not v["name"]:
        raise ValueError("Give the job a name.")
    if v["mode"] not in ("mirror", "snapshot"):
        raise ValueError("Unknown mode.")
    if not TIME_RE.match(v["run_time"]):
        raise ValueError("Daily run time must be HH:MM (24h), for example 03:00.")
    try:
        v["keep_daily"], v["keep_weekly"] = int(v["keep_daily"]), int(v["keep_weekly"])
    except ValueError:
        raise ValueError("Keep daily / keep weekly must be whole numbers.")
    if v["keep_daily"] < 1 or v["keep_weekly"] < 0:
        raise ValueError("Keep at least 1 daily copy; weekly copies can be 0 or more.")
    p = disks.check_pair(v["source"], v["dest"])
    v.update(source=p.source, dest=p.dest, src_mount=p.src_mount, dst_mount=p.dst_mount,
             src_disks=",".join(sorted(p.src_disks)), dst_disks=",".join(sorted(p.dst_disks)),
             next_run=next_occurrence(v["run_time"], datetime.now()).isoformat(timespec="seconds"))
    return v


def save_from_form(job_id):
    v = form_values(request.form)
    try:
        values = validate(dict(v))
    except (PathError, ValueError) as e:
        return render_template("job_form.html", job=v, job_id=job_id, error=str(e), drives=disks.drives()), 400
    job_id = db.save_job(values, job_id)
    flash(f"Saved. Source is on {values['src_disks']}, backup goes to {values['dst_disks']}.")
    return redirect(url_for("job_page", job_id=job_id))


DEFAULT_JOB = {"name": "", "source": "", "dest": "", "mode": "mirror", "keep_daily": 7, "keep_weekly": 4,
               "run_time": "03:00", "pre_command": "", "enabled": 1}


@app.route("/jobs/new", methods=["GET", "POST"])
def new_job():
    if request.method == "POST":
        return save_from_form(None)
    return render_template("job_form.html", job=DEFAULT_JOB, job_id=None, error=None, drives=disks.drives())


def get_job_or_404(job_id):
    job = db.job(job_id)
    if job is None:
        abort(404)
    return job


@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    job = get_job_or_404(job_id)
    if request.method == "POST":
        return save_from_form(job_id)
    return render_template("job_form.html", job=job, job_id=job_id, error=None, drives=disks.drives())


@app.get("/jobs/<int:job_id>")
def job_page(job_id):
    job = get_job_or_404(job_id)
    runs = db.runs_for(job_id)
    return render_template("job.html", job=job, runs=runs, status=job_status(job, runs[0] if runs else None))


@app.post("/jobs/<int:job_id>/run")
def run_now(job_id):
    get_job_or_404(job_id)
    flash("Backup started." if engine.enqueue(job_id) else "This job is already queued or running.")
    return redirect(request.form.get("next") or url_for("job_page", job_id=job_id))


@app.post("/jobs/<int:job_id>/delete")
def delete_job(job_id):
    job = get_job_or_404(job_id)
    if engine.state(job_id):
        flash("Cannot delete a job while it is queued or running.")
        return redirect(url_for("job_page", job_id=job_id))
    db.delete_job(job_id)
    flash(f"Deleted job '{job['name']}'. The backed-up files in {job['dest']} were left untouched.")
    return redirect(url_for("dashboard"))


LOG_TAIL_BYTES = 256 * 1024


@app.get("/runs/<int:run_id>")
def run_page(run_id):
    run = db.run(run_id) or abort(404)
    job = db.job(run["job_id"])
    path = db.log_path(run_id)
    text, truncated = "", False
    if os.path.exists(path):
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            truncated = size > LOG_TAIL_BYTES
            f.seek(max(0, size - LOG_TAIL_BYTES))
            text = f.read().decode(errors="replace")
    return render_template("run.html", run=run, job=job, log=text, truncated=truncated)


@app.get("/runs/<int:run_id>/log.txt")
def run_log(run_id):
    path = db.log_path(run_id)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="text/plain")
