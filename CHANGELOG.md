# Changelog

## 1.0.37
- Fix: verify-after-flash failed with error 87 (ReadFile, parameter is incorrect) at ~99.9%. The final read on the unbuffered device handle was not a multiple of the sector size; reads are now sector-aligned and the padding is excluded from the checksum.
- Fix: verifying a .img.gz used the compressed file size as the read-back length, so it could never match. It now uses the uncompressed image length.

## 1.0.36
- Fix verify-after-flash error (Tk variable read on the main thread).
