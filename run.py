"""run.py — Top-level entry point for PyInstaller."""
import sys
import os

# When running from source (not frozen), add src to path
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(__file__))

from src.__main__ import main

if __name__ == "__main__":
    main()
