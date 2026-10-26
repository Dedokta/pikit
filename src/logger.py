"""
logger.py — Centralised logging for PiKit.
In debug builds the console is visible, so all output appears there.
In release builds only the file handler is active.
"""
import logging
import os
import sys

LOG_DIR  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PiKit")
LOG_FILE = os.path.join(LOG_DIR, "pikit.log")

def setup(debug: bool = False):
    os.makedirs(LOG_DIR, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO
    fmt   = "%(asctime)s [%(levelname)s] %(threadName)s — %(message)s"
    datefmt = "%H:%M:%S"

    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if debug:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt,
                        handlers=handlers, force=True)
    logging.info(f"PiKit starting — debug={debug}")

log = logging.getLogger("pikit")
