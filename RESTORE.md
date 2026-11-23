# Restoring a backup

Backups are plain folders and files. You don't need this app to restore them: `rsync` or
`cp` on the host is enough. Run the commands as root (`sudo`) so owners and permissions
are kept.

## 1. Fix the machine first

- **OS drive (NVMe) died**: replace it and reinstall the OS. Mount the WD drive at
  `/mnt/bulk` again by adding it to `/etc/fstab` (find its UUID with `lsblk -f`).
- **Data drive (WD) died**: replace it, format it (`mkfs.ext4`), and mount it at
  `/mnt/bulk` again. The backups of its folders are on the NVMe.

Check that the drive holding the backup is mounted and readable:

```bash
lsblk -f
ls /mnt/bulk/backups        # or wherever the job's destination was
```

## 2. Find the backup

Each job's destination folder contains a `.backupmanager` marker file.

- **Mirror job**: the destination *is* the copy, for example `/mnt/bulk/backups/home/`.
- **Dated copies job**: the destination contains one folder per day, for example
  `2026-11-23_030000/`, and `latest` points at the newest. Pick `latest` or an older day.

## 3. Copy it back

Note the trailing slashes: they copy the *contents* of the folder.

Mirror job:

```bash
sudo rsync -aHAX --numeric-ids --info=progress2 /mnt/bulk/backups/home/ /home/ronny/ --exclude=/.backupmanager
```

Dated copies job (newest):

```bash
sudo rsync -aHAX --numeric-ids --info=progress2 /mnt/bulk/backups/home/latest/ /home/ronny/
```

A single file or folder:

```bash
sudo rsync -aHAX /mnt/bulk/backups/home/latest/Documents/report.odt /home/ronny/Documents/
```

Do **not** add `--delete` unless you want files that are not in the backup removed from
the target.

## 4. Databases

If a job used a pre-backup dump (for example `pg_dumpall.sql`), start a fresh, empty
database container and load the dump instead of reusing the copied database files:

```bash
docker exec -i my-postgres psql -U postgres < pg_dumpall.sql
```

## 5. Resume backups

`make up` in this project. Re-create the jobs if the app's `data/` folder was lost. If a
job points at the existing backup folder, it continues there because the
`.backupmanager` marker is still present. Click **Run now** once and check the result.
