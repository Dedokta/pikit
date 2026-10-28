"""
compare_card.py — read-only: compare an SD card against the image it was flashed from.

Run from an ADMIN terminal:  python compare_card.py <image.img|.img.gz> <disk number>
Reports every 4 MiB block that differs, as an absolute byte offset, plus which
partition it falls in. Opens the device GENERIC_READ only — never writes.
"""
import gzip
import struct
import sys

import win32file

CHUNK = 4 * 1024 * 1024


def partitions(h):
    _, mbr = win32file.ReadFile(h, 512)
    mbr = bytes(mbr)
    out = []
    for i in range(4):
        e = mbr[446 + i * 16: 462 + i * 16]
        start, n = struct.unpack_from("<II", e, 8)
        if n:
            out.append((i + 1, start * 512, (start + n) * 512))
    win32file.SetFilePointer(h, 0, win32file.FILE_BEGIN)
    return out


def which(parts, off):
    for num, a, b in parts:
        if a <= off < b:
            return f"partition {num}"
    return "before first partition / gap"


def main(img, disk):
    opener = gzip.open if img.lower().endswith(".gz") else open
    h = win32file.CreateFile(
        rf"\\.\PhysicalDrive{disk}", win32file.GENERIC_READ,
        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
        None, win32file.OPEN_EXISTING, win32file.FILE_FLAG_NO_BUFFERING, None)
    parts = partitions(h)
    print("partitions:", [(n, a, b - a) for n, a, b in parts])
    pos = bad = 0
    with opener(img, "rb") as f:
        while chunk := f.read(CHUNK):
            want = ((len(chunk) + 511) // 512) * 512
            _, data = win32file.ReadFile(h, want)
            data = bytes(data[:len(chunk)])
            if data != chunk:
                bad += 1
                diff = [i for i in range(len(chunk)) if data[i:i + 1] != chunk[i:i + 1]]
                first = pos + diff[0]
                print(f"DIFF block @ {pos:>12}: {len(diff)} bytes differ, "
                      f"first at {first} (sector {first // 512}), "
                      f"{which(parts, first)}")
                if bad >= 20:
                    print("stopping after 20 differing blocks")
                    break
            pos += len(chunk)
    print(f"compared {pos} bytes, {bad} differing block(s)")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
