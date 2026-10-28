"""
disk.py — Physical disk detection, smart-boundary backup, and raw flash write.

Smart backup: parses the MBR partition table to find where the last partition ends,
then only reads up to that byte offset. Skips all empty trailing space.
Typical saving: 20-25 GB on a 32 GB card used by a Pi OS image.
"""
import os
import struct
import subprocess
import json
import time
import gzip
import logging

import win32file
import win32con

log = logging.getLogger("pikit")

SECTOR    = 512
BUFFER    = 4 * 1024 * 1024  # 4 MB read/write chunks
MAX_BAD_BLOCKS = 4           # verify stops counting after this many bad chunks

FSCTL_LOCK_VOLUME    = 0x00090018
FSCTL_DISMOUNT_VOLUME= 0x00090020
FSCTL_UNLOCK_VOLUME  = 0x0009001C


# ── Drive detection ────────────────────────────────────────────────────────────

class DriveInfo:
    def __init__(self, index, device, name, size_bytes, letters):
        self.index      = index
        self.device     = device       # e.g. \\.\PhysicalDrive1
        self.name       = name
        self.size_bytes = int(size_bytes) if size_bytes else 0
        self.letters    = letters      # e.g. ['E:']

    @property
    def size_str(self):
        gb = self.size_bytes / 1_073_741_824
        return f"{gb:.1f} GB"

    @property
    def letters_str(self):
        return "  ".join(self.letters) if self.letters else "(no drive letter)"

    def __repr__(self):
        return f"<Drive {self.device} {self.name} {self.size_str}>"


def list_usb_drives(removable_only=True):
    """Return list of DriveInfo for non-boot disks.
    removable_only=True (default): USB bus type only — hides internal SATA/NVMe.
    """
    ps = r"""
# Exclude the disk(s) that contain the Windows boot/system partition.
# This is safer than filtering by BusType, which misses many card readers.
$bootDiskNumbers = @(
    Get-Partition | Where-Object { $_.IsSystem -or $_.IsBoot } |
        Select-Object -ExpandProperty DiskNumber -Unique
)
$drives = Get-Disk | Where-Object { $_.Number -notin $bootDiskNumbers }
$result = foreach ($d in $drives) {
    $letters = @()
    try {
        $letters = Get-Partition -DiskNumber $d.Number -EA SilentlyContinue |
                   Where-Object { $_.DriveLetter -and ($_.DriveLetter -ne [char]0) } |
                   ForEach-Object { [string]$_.DriveLetter + ':' }
    } catch {}
    [PSCustomObject]@{
        Index   = [int]$d.Number
        Device  = ('\\.\PhysicalDrive' + $d.Number)
        Name    = [string]$d.FriendlyName
        Size    = [long]$d.Size
        BusType = [string]$d.BusType
        Letters = @($letters)
    }
}
$result | ConvertTo-Json -Depth 3
"""
    log.debug("list_usb_drives() — running PowerShell")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log.debug(f"list_usb_drives() stdout={r.stdout[:200]!r}  stderr={r.stderr[:200]!r}")
        raw = r.stdout.strip()
        if not raw:
            log.debug("list_usb_drives() — empty stdout, returning []")
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        out = []
        for d in data:
            letters = d.get("Letters") or []
            if isinstance(letters, str):
                letters = [letters] if letters else []
            name = d.get("Name", "Unknown Drive")
            bus  = d.get("BusType", "")
            if bus and bus not in name:
                name = f"{name}  [{bus}]"
            out.append(DriveInfo(
                index      = d["Index"],
                device     = d["Device"],
                name       = name,
                size_bytes = d.get("Size", 0),
                letters    = list(letters),
            ))
        # Filter out zero-size entries (empty card reader slots)
        out = [d for d in out if d.size_bytes > 0]
        # Optionally restrict to USB/removable drives only (hides internal SATA/NVMe)
        if removable_only:
            out = [d for d in out if "[USB]" in d.name]
        log.debug(f"list_usb_drives() — found {len(out)} drive(s):")
        for d in out:
            log.debug(f"  {d}  letters={d.letters}")
        return out
    except Exception:
        log.exception("list_usb_drives() failed")
        return []


# ── MBR partition boundary ─────────────────────────────────────────────────────

def get_smart_backup_size(device_path):
    """
    Read the MBR from device_path, parse the four primary partition entries,
    and return the byte offset of the end of the last partition.

    Returns None if:
    - MBR signature is invalid
    - No valid partitions found
    - Any read error

    Caller should fall back to full disk size if None is returned.
    """
    log.debug(f"get_smart_backup_size({device_path})")
    try:
        with open(device_path, "rb") as f:
            mbr = f.read(SECTOR)
        if len(mbr) < SECTOR or mbr[510:512] != b"\x55\xAA":
            log.debug("get_smart_backup_size — bad MBR signature")
            return None
        max_end = 0
        for i in range(4):
            off   = 446 + i * 16
            entry = mbr[off:off+16]
            if entry[4] == 0:          # empty slot
                continue
            lba_start   = struct.unpack_from("<I", entry, 8)[0]
            num_sectors = struct.unpack_from("<I", entry, 12)[0]
            end         = lba_start + num_sectors
            if end > max_end:
                max_end = end
        result = max_end * SECTOR if max_end > 0 else None
        log.debug(f"get_smart_backup_size — {result} bytes ({(result or 0)/1e9:.2f} GB)")
        return result
    except Exception:
        log.exception(f"get_smart_backup_size({device_path}) failed")
        return None


def get_disk_size(index):
    """Return total disk size in bytes via PowerShell."""
    ps = f"(Get-Disk -Number {index}).Size"
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return int(r.stdout.strip())
    except Exception:
        return 0


# ── Backup (disk → .img) ───────────────────────────────────────────────────────

def backup_disk(drive: DriveInfo, out_path: str, smart=True,
                progress_cb=None, cancel_event=None):
    """
    Read a physical disk to a raw .img file.

    smart=True  — stop reading at the end of the last MBR partition (recommended).
    smart=False — read the entire disk sector by sector.

    progress_cb(bytes_done, bytes_total, speed_bps)
    cancel_event: threading.Event — set to abort.

    Returns the path written, or raises on error.
    """
    log.info(f"backup_disk: {drive.device}  smart={smart}  → {out_path}")
    if smart:
        total = get_smart_backup_size(drive.device)
        if total:
            # Round up to next sector boundary (should already be aligned)
            total = ((total + SECTOR - 1) // SECTOR) * SECTOR
            log.info(f"backup_disk: smart boundary = {total} bytes ({total/1e9:.2f} GB)")
        else:
            log.warning("backup_disk: smart boundary unavailable — falling back to full disk")
            smart = False  # fall back

    if not smart or not total:
        total = drive.size_bytes or get_disk_size(drive.index)
        log.info(f"backup_disk: full disk size = {total} bytes ({total/1e9:.2f} GB)")

    log.debug(f"backup_disk: opening {drive.device}")
    handle = win32file.CreateFile(
        drive.device,
        win32file.GENERIC_READ,
        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
        None,
        win32file.OPEN_EXISTING,
        win32file.FILE_FLAG_NO_BUFFERING | win32file.FILE_FLAG_SEQUENTIAL_SCAN,
        None,
    )

    start = time.time()
    done  = 0

    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            while True:
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("Cancelled by user")
                chunk = min(BUFFER, total - done) if total else BUFFER
                if chunk <= 0:
                    break
                # Align to sector size
                chunk = ((chunk + SECTOR - 1) // SECTOR) * SECTOR
                _, data = win32file.ReadFile(handle, chunk)
                if not data:
                    break
                f.write(data)
                done += len(data)
                elapsed = time.time() - start
                speed   = done / elapsed if elapsed > 0.1 else 0
                if progress_cb:
                    progress_cb(done, total, speed)
                if total and done >= total:
                    break
    finally:
        win32file.CloseHandle(handle)

    return out_path


# ── Volume lock helpers ────────────────────────────────────────────────────────

def _lock_volumes(disk_index):
    """
    Lock and dismount every mounted volume on disk_index.

    FSCTL_LOCK_VOLUME must be sent to the *volume* handle (e.g. \\.\L:),
    not the physical-disk handle.  Returns the list of open volume handles
    so the caller can close them after the write is done.
    """
    ps = f"""
Get-Partition -DiskNumber {disk_index} -ErrorAction SilentlyContinue |
    Where-Object {{ $_.DriveLetter -and ($_.DriveLetter -ne [char]0) }} |
    ForEach-Object {{ $_.DriveLetter }}
"""
    locked = []
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        letters = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        log.info(f"_lock_volumes: disk {disk_index} letters={letters}")
        for letter in letters:
            vol = f"\\\\.\\{letter}:"
            try:
                h = win32file.CreateFile(
                    vol,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                    None, win32file.OPEN_EXISTING, 0, None,
                )
                win32file.DeviceIoControl(h, FSCTL_LOCK_VOLUME,    None, 0, None)
                win32file.DeviceIoControl(h, FSCTL_DISMOUNT_VOLUME, None, 0, None)
                locked.append(h)
                log.info(f"_lock_volumes: locked {vol}")
            except Exception as e:
                log.warning(f"_lock_volumes: could not lock {vol}: {e}")
    except Exception:
        log.exception("_lock_volumes failed")
    return locked


# ── Flash (img or img.gz → disk) ──────────────────────────────────────────────

def _gz_uncompressed_size(path):
    """Read the ISIZE field from the gzip footer (last 4 bytes).
    Valid for files < 4 GB uncompressed; Pi images are well within that."""
    try:
        with open(path, "rb") as f:
            f.seek(-4, 2)
            return struct.unpack("<I", f.read(4))[0]
    except Exception:
        return 0


def _partition_ranges(mbr):
    """(number, start_byte, end_byte) for each MBR partition in a 512-byte sector."""
    out = []
    for i in range(4):
        e = mbr[446 + i * 16: 462 + i * 16]
        if len(e) < 16:
            break
        start, n = struct.unpack_from("<II", e, 8)
        if n:
            out.append((i + 1, start * SECTOR, (start + n) * SECTOR))
    return out


def partition_of(parts, offset):
    for num, a, b in parts:
        if a <= offset < b:
            return num
    return None


def compare_to_image(handle, img_path, progress_cb=None, cancel_event=None):
    """
    Re-read the disk from byte 0 through `handle` and compare it with the image.

    Reads through the handle used for the write, so Windows has not yet been
    told to re-mount the card and cannot have touched it.  Returns a dict:
      total   — image bytes compared
      diff    — number of differing bytes
      first   — byte offset of the first difference (or None)
      parts   — {partition number: differing bytes}, key None = outside partitions
    """
    is_gz    = img_path.lower().endswith(".gz")
    src_size = os.path.getsize(img_path)
    win32file.SetFilePointer(handle, 0, win32file.FILE_BEGIN)

    raw_f = open(img_path, "rb")
    src   = gzip.GzipFile(fileobj=raw_f) if is_gz else raw_f
    res   = {"total": 0, "diff": 0, "first": None, "parts": {}, "truncated": False}
    ranges = []
    pos = bad_blocks = 0
    try:
        while True:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Cancelled by user")
            chunk = src.read(BUFFER)
            if not chunk:
                break
            if pos == 0:
                ranges = _partition_ranges(chunk[:SECTOR])
            want = ((len(chunk) + SECTOR - 1) // SECTOR) * SECTOR
            _, data = win32file.ReadFile(handle, want)
            data = bytes(data[:len(chunk)])
            if data != chunk:
                bad_blocks += 1
                for s in range(0, len(chunk), SECTOR):   # only walk bad sectors
                    if data[s:s + SECTOR] == chunk[s:s + SECTOR]:
                        continue
                    for i in range(s, min(s + SECTOR, len(chunk))):
                        if i >= len(data) or data[i] != chunk[i]:
                            res["diff"] += 1
                            if res["first"] is None:
                                res["first"] = pos + i
                            p = partition_of(ranges, pos + i)
                            res["parts"][p] = res["parts"].get(p, 0) + 1
            pos += len(chunk)
            if bad_blocks > MAX_BAD_BLOCKS:   # clearly bad — stop counting
                res["truncated"] = True
                break
            if progress_cb:
                progress_cb(raw_f.tell() if is_gz else pos, src_size, 0)
    finally:
        raw_f.close()
    res["total"] = pos
    return res


def flash_disk(img_path: str, drive: DriveInfo,
               progress_cb=None, cancel_event=None,
               verify=False, verify_cb=None):
    """
    Write a .img or .img.gz file to a physical disk.

    progress_cb(bytes_done, bytes_total, speed_bps)
      bytes_done/total are compressed bytes when source is .gz
      (accurate enough for a progress bar)
    cancel_event: threading.Event

    Locks and dismounts all volumes on the target disk before writing.
    If verify is True, the card is compared with the image through the same
    open handle (so Windows cannot re-mount and modify it first) and the
    compare_to_image() result dict is returned; otherwise returns None.
    """
    is_gz    = img_path.lower().endswith(".gz")
    src_size = os.path.getsize(img_path)
    # For progress we track compressed bytes in; close enough.
    total    = src_size

    # Lock every volume on the target disk BEFORE opening it for writing.
    vol_handles = _lock_volumes(drive.index)

    handle = win32file.CreateFile(
        drive.device,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
        None,
        win32file.OPEN_EXISTING,
        win32file.FILE_FLAG_NO_BUFFERING | win32file.FILE_FLAG_WRITE_THROUGH,
        None,
    )

    try:
        src_done = 0
        start    = time.time()

        # For .gz: open the raw file separately so we can track compressed
        # bytes consumed (raw_f.tell()) rather than uncompressed bytes out.
        # This keeps progress 0→100% correctly against the on-disk file size.
        if is_gz:
            raw_f = open(img_path, "rb")
            src   = gzip.GzipFile(fileobj=raw_f)
        else:
            raw_f = None
            src   = open(img_path, "rb")

        with src:
            while True:
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("Cancelled by user")
                data = src.read(BUFFER)
                if not data:
                    break
                # Pad to sector boundary
                rem = len(data) % SECTOR
                if rem:
                    data = data + b"\x00" * (SECTOR - rem)
                win32file.WriteFile(handle, data)
                src_done = raw_f.tell() if raw_f else src.tell()
                elapsed  = time.time() - start
                speed    = src_done / elapsed if elapsed > 0.1 else 0
                if progress_cb:
                    progress_cb(src_done, total, speed)
        if raw_f:
            raw_f.close()

        if verify:
            return compare_to_image(handle, img_path,
                                    progress_cb=verify_cb,
                                    cancel_event=cancel_event)
    finally:
        try:
            win32file.DeviceIoControl(handle, FSCTL_UNLOCK_VOLUME, None, 0, None)
        except Exception:
            pass
        win32file.CloseHandle(handle)
        for vh in vol_handles:
            try:
                win32file.CloseHandle(vh)
            except Exception:
                pass
