"""
compress.py — Streaming gzip compress / decompress with progress callbacks.
"""
import gzip
import os
import time

BUFFER = 4 * 1024 * 1024  # 4 MB


def compress_image(src_path: str, dst_path: str, level: int = 6,
                   progress_cb=None, cancel_event=None) -> str:
    """
    Compress src_path (.img) → dst_path (.img.gz).

    progress_cb(bytes_read, bytes_total, speed_bps)
    Returns dst_path on success, raises on error/cancel.
    """
    total = os.path.getsize(src_path)
    done  = 0
    start = time.time()

    os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)

    with open(src_path, "rb") as src, \
         gzip.open(dst_path, "wb", compresslevel=level) as dst:
        while True:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Cancelled by user")
            data = src.read(BUFFER)
            if not data:
                break
            dst.write(data)
            done   += len(data)
            elapsed = time.time() - start
            speed   = done / elapsed if elapsed > 0.1 else 0
            if progress_cb:
                progress_cb(done, total, speed)

    return dst_path


def decompress_image(src_path: str, dst_path: str,
                     progress_cb=None, cancel_event=None) -> str:
    """
    Decompress src_path (.img.gz) → dst_path (.img).

    progress_cb(compressed_bytes_read, total_compressed, speed_bps)
    Returns dst_path on success.
    """
    total = os.path.getsize(src_path)
    done  = 0
    start = time.time()

    os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)

    with gzip.open(src_path, "rb") as src, open(dst_path, "wb") as dst:
        while True:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Cancelled by user")
            data = src.read(BUFFER)
            if not data:
                break
            dst.write(data)
            done   += len(data)
            elapsed = time.time() - start
            speed   = done / elapsed if elapsed > 0.1 else 0
            if progress_cb:
                progress_cb(done, total, speed)

    return dst_path
