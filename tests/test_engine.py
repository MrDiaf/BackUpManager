import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

import engine
from engine import RunFailed, RunRefused

HAS_RSYNC = shutil.which("rsync") is not None


class Schedule(unittest.TestCase):
    def test_later_today(self):
        self.assertEqual(engine.next_occurrence("03:00", datetime(2026, 1, 5, 1, 0)), datetime(2026, 1, 5, 3, 0))

    def test_already_passed_goes_to_tomorrow(self):
        self.assertEqual(engine.next_occurrence("03:00", datetime(2026, 1, 5, 3, 0)), datetime(2026, 1, 6, 3, 0))
        self.assertEqual(engine.next_occurrence("03:00", datetime(2026, 12, 31, 9, 0)), datetime(2027, 1, 1, 3, 0))


class Retention(unittest.TestCase):
    def test_keeps_daily_and_weekly(self):
        # one snapshot a day for 60 days
        start = datetime(2026, 1, 1, 3, 0, 0)
        names = [(start + timedelta(days=i)).strftime(engine.SNAPSHOT_FMT) for i in range(60)]
        keep = engine.snapshots_to_keep(names, keep_daily=7, keep_weekly=4)
        newest7 = sorted(names)[-7:]
        self.assertTrue(set(newest7) <= keep)
        # 4 weekly = newest of the 4 most recent ISO weeks; those overlapping the daily
        # window are already counted, so only older weeks add extra snapshots
        self.assertLessEqual(len(keep), 7 + 4)
        self.assertGreater(len(keep), 7)
        self.assertNotIn(sorted(names)[0], keep)

    def test_several_runs_same_day_keep_newest(self):
        names = ["2026-01-05_030000", "2026-01-05_120000", "2026-01-04_030000"]
        self.assertEqual(engine.snapshots_to_keep(names, 2, 0), {"2026-01-05_120000", "2026-01-04_030000"})

    def test_ignores_foreign_names(self):
        self.assertEqual(engine.snapshots_to_keep(["latest", ".incomplete", "notes"], 7, 4), set())


class Stats(unittest.TestCase):
    def test_parse_total_size(self):
        self.assertEqual(engine.parse_total_size("Number of files: 3\nTotal file size: 1,234,567 bytes\n"), 1234567)
        self.assertIsNone(engine.parse_total_size("nothing"))


class Destination(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = open(os.path.join(self.tmp.name, "log"), "w+")
        self.host = mock.patch.object(engine.disks, "HOST_ROOT", self.tmp.name)
        self.host.start()

    def tearDown(self):
        self.host.stop()
        self.log.close()
        self.tmp.cleanup()

    def test_new_destination_gets_marker(self):
        dst = os.path.join(self.tmp.name, "new", "dest")
        engine.prepare_destination(dst, 1, self.log)
        self.assertTrue(os.path.isfile(os.path.join(dst, engine.MARKER)))
        engine.prepare_destination(dst, 1, self.log)  # second time: fine

    def test_foreign_non_empty_destination_refused(self):
        dst = os.path.join(self.tmp.name, "full")
        os.makedirs(dst)
        open(os.path.join(dst, "precious.txt"), "w").close()
        with self.assertRaisesRegex(RunRefused, "not empty"):
            engine.prepare_destination(dst, 1, self.log)

    def test_empty_source_refused(self):
        src = os.path.join(self.tmp.name, "empty")
        os.makedirs(src)
        with self.assertRaisesRegex(RunRefused, "empty"):
            engine.check_source_not_empty(src)

    def test_failing_pre_command_fails_run(self):
        with self.assertRaisesRegex(RunFailed, "exit code 3"):
            engine.run_pre_command("echo hi; exit 3", self.tmp.name, self.tmp.name, self.log)

    def test_pre_command_runs_in_source(self):
        engine.run_pre_command("echo dumped > dump.sql", self.tmp.name, self.tmp.name, self.log)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "dump.sql")))


class UnmountedDrive(unittest.TestCase):
    def test_run_refused_when_destination_mount_changed(self):
        job = {"source": "/home/me", "dest": "/mnt/bulk/b", "src_mount": "/", "dst_mount": "/mnt/bulk",
               "dst_disks": "sdb"}
        # /mnt/bulk not mounted: everything resolves to the root filesystem
        with mock.patch.object(engine.disks, "HOST_ROOT", "/"), \
             mock.patch.object(engine.disks, "nearest_existing", lambda p: p), \
             mock.patch.object(engine.disks, "to_host", lambda p: p), \
             mock.patch.object(engine.disks, "to_container", lambda p: p), \
             mock.patch.object(engine.disks, "mount_point", lambda p: "/"):
            with self.assertRaisesRegex(RunRefused, "Destination drive is not mounted"):
                engine.check_before_run(job)


@unittest.skipUnless(HAS_RSYNC, "rsync not installed")
class RsyncModes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "src")
        self.dst = os.path.join(self.tmp.name, "dst")
        os.makedirs(self.src)
        with open(os.path.join(self.src, "a.txt"), "w") as f:
            f.write("hello")
        self.log = open(os.path.join(self.tmp.name, "log"), "w+")
        self.host = mock.patch.object(engine.disks, "HOST_ROOT", self.tmp.name)
        self.host.start()
        engine.prepare_destination(self.dst, 1, self.log)

    def tearDown(self):
        self.host.stop()
        self.log.close()
        self.tmp.cleanup()

    def test_mirror_deletes_extras_but_keeps_marker(self):
        size = engine.run_mirror(self.src, self.dst, self.log)
        self.assertEqual(size, 5)
        os.remove(os.path.join(self.src, "a.txt"))
        open(os.path.join(self.src, "b.txt"), "w").close()
        engine.run_mirror(self.src, self.dst, self.log)
        self.assertEqual(sorted(os.listdir(self.dst)), [engine.MARKER, "b.txt"])

    def test_snapshots_hardlink_and_prune(self):
        for day in (1, 2, 3):
            engine.run_snapshot(self.src, self.dst, self.log, keep_daily=2, keep_weekly=0,
                                now=datetime(2026, 1, day, 3))
        entries = sorted(os.listdir(self.dst))
        self.assertEqual(entries, [engine.MARKER, "2026-01-02_030000", "2026-01-03_030000", "latest"])
        self.assertEqual(os.readlink(os.path.join(self.dst, "latest")), "2026-01-03_030000")
        a2 = os.stat(os.path.join(self.dst, "2026-01-02_030000", "a.txt"))
        a3 = os.stat(os.path.join(self.dst, "2026-01-03_030000", "a.txt"))
        self.assertEqual(a2.st_ino, a3.st_ino)  # unchanged file is hard-linked, not copied


if __name__ == "__main__":
    unittest.main()
