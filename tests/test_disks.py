import os
import tempfile
import unittest
from unittest import mock

import disks
from disks import PathError


class PathRules(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(disks.normalize(" /mnt/bulk/../bulk/x/ "), "/mnt/bulk/x")
        self.assertEqual(disks.normalize("//etc"), "/etc")
        with self.assertRaises(PathError):
            disks.normalize("relative/path")

    def test_is_within(self):
        self.assertTrue(disks.is_within("/a/b", "/a"))
        self.assertTrue(disks.is_within("/a", "/a"))
        self.assertTrue(disks.is_within("/anything", "/"))
        self.assertFalse(disks.is_within("/ab", "/a"))


class PhysicalDisks(unittest.TestCase):
    """Fake sysfs layouts: a partition maps to its disk, LVM maps through slaves/."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        sda1 = os.path.join(root, "devices", "pci", "block", "sda", "sda1")
        os.makedirs(sda1)
        open(os.path.join(sda1, "partition"), "w").close()
        nvme_p3 = os.path.join(root, "devices", "pci", "block", "nvme0n1", "nvme0n1p3")
        os.makedirs(nvme_p3)
        open(os.path.join(nvme_p3, "partition"), "w").close()
        dm = os.path.join(root, "devices", "virtual", "block", "dm-0")
        os.makedirs(os.path.join(dm, "slaves"))
        os.symlink(nvme_p3, os.path.join(dm, "slaves", "nvme0n1p3"))
        self.sda1, self.dm = sda1, dm

    def tearDown(self):
        self.tmp.cleanup()

    def test_partition_maps_to_disk(self):
        self.assertEqual(disks._physical_disks(self.sda1), {"sda"})

    def test_lvm_maps_to_underlying_disk(self):
        self.assertEqual(disks._physical_disks(self.dm), {"nvme0n1"})


class CheckPair(unittest.TestCase):
    """check_pair against a fake host root where 'disk' is decided by top-level folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in ("home/me", "mnt/bulk/backups", "mnt/bulk/data"):
            os.makedirs(os.path.join(self.root, d))
        os.symlink(os.path.join(self.root, "mnt/bulk"), os.path.join(self.root, "bulklink"))

        def fake_disks(cpath):
            return {"sdb"} if disks.to_host(cpath).startswith("/mnt/bulk") else {"nvme0n1"}

        def fake_mount(cpath):
            return os.path.join(self.root, "mnt/bulk") if disks.to_host(cpath).startswith("/mnt/bulk") else self.root

        self.patches = [mock.patch.object(disks, "HOST_ROOT", self.root),
                        mock.patch.object(disks, "disks_of", fake_disks),
                        mock.patch.object(disks, "mount_point", fake_mount)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_different_drives_accepted(self):
        p = disks.check_pair("/home/me", "/mnt/bulk/backups/home")
        self.assertEqual((p.src_disks, p.dst_disks), ({"nvme0n1"}, {"sdb"}))
        self.assertEqual((p.src_mount, p.dst_mount), ("/", "/mnt/bulk"))

    def test_reverse_direction_accepted(self):
        disks.check_pair("/mnt/bulk/data", "/home/me/bulk-backup")

    def test_same_drive_refused(self):
        with self.assertRaisesRegex(PathError, "same physical drive"):
            disks.check_pair("/home/me", "/srv/backup")

    def test_nested_paths_refused(self):
        with self.assertRaisesRegex(PathError, "inside the source"):
            disks.check_pair("/mnt/bulk", "/mnt/bulk/backups")
        with self.assertRaisesRegex(PathError, "inside the destination"):
            disks.check_pair("/mnt/bulk/backups/x", "/mnt/bulk/backups")

    def test_missing_source_refused(self):
        with self.assertRaisesRegex(PathError, "does not exist"):
            disks.check_pair("/home/nobody", "/mnt/bulk/backups/x")

    def test_symlink_refused(self):
        with self.assertRaisesRegex(PathError, "symlink"):
            disks.check_pair("/home/me", "/bulklink/backups")


class RealContainerMounts(unittest.TestCase):
    """Runs against the real /host mount when the tests run inside the app container."""

    @unittest.skipUnless(os.path.isdir("/host/proc"), "host filesystem not mounted")
    def test_host_root_has_a_physical_disk(self):
        self.assertTrue(disks.disks_of("/host"))
        self.assertTrue(any(d["mount"] == "/" for d in disks.drives()))


if __name__ == "__main__":
    unittest.main()
