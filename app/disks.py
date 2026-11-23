"""Which physical disk is a path on, and is it mounted?

Users type host paths (e.g. /mnt/bulk/backup). Inside the container the host's
root filesystem is at HOST_ROOT, so /mnt/bulk/backup is /host/mnt/bulk/backup.
"""
import os
from dataclasses import dataclass

HOST_ROOT = os.environ.get("HOST_ROOT", "/host")
HOST_HOME = os.environ.get("HOST_HOME", "")  # $HOME of the user who ran `make up`; what ~ means
MAX_SYMLINKS = 40
SYS_ROOT = "/sys"
MOUNTINFO = "/proc/self/mountinfo"


class PathError(ValueError):
    """A path or source/destination pair that must be refused."""


# --- host <-> container paths -------------------------------------------------

def normalize(host_path):
    p = (host_path or "").strip()
    if p == "~" or p.startswith("~/"):
        if not HOST_HOME:
            raise PathError("Don't know which home folder ~ is. Enter the full path, starting with /.")
        p = HOST_HOME + p[1:]
    if not p.startswith("/"):
        raise PathError(f"'{p}' is not a full path. Start it with / (or ~ for your home folder), or use Browse.")
    p = "/" + os.path.normpath(p).lstrip("/")
    return p


def to_container(host_path):
    return HOST_ROOT if host_path == "/" else HOST_ROOT + host_path


def to_host(container_path):
    if container_path == HOST_ROOT:
        return "/"
    if container_path.startswith(HOST_ROOT + "/"):
        return container_path[len(HOST_ROOT):]
    raise PathError(f"{container_path} is outside the host filesystem.")


def is_within(child, parent):
    """True if host path `child` is `parent` or inside it."""
    return child == parent or parent == "/" or child.startswith(parent.rstrip("/") + "/")


def resolve(host_path):
    """The real host path, following symlinks the way the host would.

    os.path.realpath can't be used: an absolute symlink target like /mnt/bulk means
    /host/mnt/bulk inside the container. Missing trailing parts are kept as typed.
    """
    parts = [p for p in normalize(host_path).split("/") if p]
    current, hops = "/", 0
    while parts:
        part = parts.pop(0)
        if part == ".":
            continue
        if part == "..":
            current = os.path.dirname(current)
            continue
        candidate = os.path.join(current, part)
        if os.path.islink(to_container(candidate)):
            hops += 1
            if hops > MAX_SYMLINKS:
                raise PathError(f"Too many symlinks in {host_path}.")
            target = os.readlink(to_container(candidate))
            if target.startswith("/"):
                current = "/"
            parts = [p for p in target.split("/") if p] + parts
            continue
        current = candidate
    return current


def nearest_existing(container_path):
    p = container_path
    while not os.path.exists(p):
        p = os.path.dirname(p)
    return p


# --- mounts -----------------------------------------------------------------------

def _unescape(s):
    return s.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def mounts():
    """[(mount_point, fstype, source)] from mountinfo, in order."""
    result = []
    with open(MOUNTINFO) as f:
        for line in f:
            left, _, right = line.partition(" - ")
            fields = left.split()
            fstype, source = right.split()[:2]
            result.append((_unescape(fields[4]), fstype, _unescape(source)))
    return result


def mount_point(container_path):
    """The container mount point that holds container_path (longest prefix wins)."""
    best = None
    for mp, _, _ in mounts():
        if container_path == mp or container_path.startswith(mp.rstrip("/") + "/"):
            if best is None or len(mp) >= len(best):
                best = mp
    return best


# --- physical disks ---------------------------------------------------------------

def _physical_disks(sys_dev_path):
    """Physical disk names behind a /sys/devices/... block device path.

    Partitions map to their parent disk; device-mapper / md devices (LVM, LUKS,
    RAID) map to every disk listed under slaves/.
    """
    real = os.path.realpath(sys_dev_path)
    slaves = os.path.join(real, "slaves")
    if os.path.isdir(slaves) and os.listdir(slaves):
        disks = set()
        for s in os.listdir(slaves):
            disks |= _physical_disks(os.path.join(slaves, s))
        return disks
    if os.path.exists(os.path.join(real, "partition")):
        real = os.path.dirname(real)
    return {os.path.basename(real)}


def _disks_from_mount_source(container_path):
    # Filesystems like btrfs report an anonymous st_dev; fall back to the mount's device.
    mp = mount_point(container_path)
    for m, _, source in reversed(mounts()):
        if m == mp:
            name = os.path.basename(source)
            sys_path = os.path.join(SYS_ROOT, "class", "block", name)
            if source.startswith("/dev/") and os.path.exists(sys_path):
                return _physical_disks(sys_path)
            break
    raise PathError(f"Cannot tell which physical drive {to_host(container_path)} is on, so it is refused.")


def disks_of(container_path):
    """Set of physical disk names (e.g. {'nvme0n1'}) holding an existing path."""
    st = os.stat(container_path)
    sys_path = os.path.join(SYS_ROOT, "dev", "block", f"{os.major(st.st_dev)}:{os.minor(st.st_dev)}")
    if os.path.exists(sys_path):
        return _physical_disks(sys_path)
    return _disks_from_mount_source(container_path)


def disk_label(name):
    try:
        with open(os.path.join(SYS_ROOT, "block", name, "device", "model")) as f:
            model = f.read().strip()
        return f"{name} ({model})" if model else name
    except OSError:
        return name


# --- the pair check -------------------------------------------------------------------

@dataclass
class Placement:
    source: str
    dest: str
    src_mount: str
    dst_mount: str
    src_disks: set
    dst_disks: set


def check_pair(source, dest):
    """Validate a source/destination pair of host paths. Raises PathError."""
    source, dest = resolve(source), resolve(dest)
    if is_within(dest, source):
        raise PathError("The destination is inside the source. It would back itself up.")
    if is_within(source, dest):
        raise PathError("The source is inside the destination.")

    csrc, cdst = to_container(source), to_container(dest)
    if not os.path.isdir(csrc):
        raise PathError(f"Source folder {source} does not exist.")
    if os.path.exists(cdst) and not os.path.isdir(cdst):
        raise PathError(f"Destination {dest} exists and is not a folder.")
    cdst_existing = nearest_existing(cdst)

    src_disks, dst_disks = disks_of(csrc), disks_of(cdst_existing)
    shared = src_disks & dst_disks
    if shared:
        raise PathError(
            f"Source and destination are on the same physical drive ({', '.join(sorted(shared))}). "
            "The backup must go on a different drive. (If you expected another drive here, check that it is mounted.)")
    return Placement(source, dest, to_host(mount_point(csrc)), to_host(mount_point(cdst_existing)),
                     src_disks, dst_disks)


# --- drives overview --------------------------------------------------------------

def drives():
    """One entry per mounted block-device filesystem on the host, for the dashboard."""
    seen, result = set(), []
    for mp, fstype, source in mounts():
        if not (mp == HOST_ROOT or mp.startswith(HOST_ROOT + "/")):
            continue
        if not source.startswith("/dev/") or "/loop" in source or source in seen:
            continue
        seen.add(source)
        try:
            st = os.statvfs(mp)
            disks = disks_of(mp)
        except (OSError, PathError):
            continue
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        result.append({
            "mount": to_host(mp), "device": source, "fstype": fstype,
            "disk": ", ".join(disk_label(d) for d in sorted(disks)),
            "total": total, "free": free, "used": total - st.f_bfree * st.f_frsize,
        })
    return sorted(result, key=lambda d: d["mount"])
