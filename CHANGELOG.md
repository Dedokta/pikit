# Changelog

## 1.0.38
- Fix: verify no longer fails because Windows re-mounted and touched the card after the write. The card is now compared with the image through the same open write handle, so it stays locked until verify finishes.
- Verify now compares bytes directly and reports exactly how many bytes differ, the first offset, and which partition they are in, so a one-byte difference can be told apart from a bad write.
- Cancel now works during verify.
- build.ps1 now finds Inno Setup in the per-user install folder.

## 1.0.37
- Fix: verify-after-flash failed with error 87 (ReadFile, parameter is incorrect) at ~99.9%. The final read on the unbuffered device handle was not a multiple of the sector size; reads are now sector-aligned and the padding is excluded from the checksum.
- Fix: verifying a .img.gz used the compressed file size as the read-back length, so it could never match. It now uses the uncompressed image length.

## 1.0.36
- Fix verify-after-flash error (Tk variable read on the main thread).
