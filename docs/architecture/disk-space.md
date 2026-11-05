# Disk space on the robot (R5, 2026-11-05)

SD card root: 14 GB. Start of R5: 1.7 GB free (88% used). End: 3.3 GB free (76% used).

## What we did
1. Cleared safe caches (about +528 MB). Kept: Hugging Face speech models (needed), Pollen system folders, the Signal Docker image.
2. Capped the swap file (about +1.1 GB), see below.

## Swap file finding
- `/var/swap` is NOT leftover. It is the writeback backing file of zram (`/dev/loop0`), created by `rpi-resize-swap-file.service` at every boot.
- Default size = min(RAM x 1, 2048 MiB, 50% of free disk). It was 1678 MiB and would have grown back after every cleanup.
- RAM is 3.8 GB and use is about 0.6 GB. zram holds almost nothing, so the file is only a safety net.
- Change: drop-in `/etc/rpi/swap.conf.d/50-lola-bla.conf` with `[File]` / `MaxSizeMiB=512`. Pollen's own files are untouched.
- Verified after restart: `/var/swap` = 536870912 bytes, loop0 attached, zram swap active, daemon active.
- Undo: `sudo rm /etc/rpi/swap.conf.d/50-lola-bla.conf`, then restart.

## Big items left (not touched)
| Item | Size | Note |
|---|---|---|
| Signal API Docker image | 1.36 GB | needed |
| HF whisper-small.en | 461 MB | needed |
| HF Kokoro-82M | 310 MB | needed (daemon also ships a copy) |
| HF whisper-tiny.en | 72 MB | maybe unused, ask before removing |
| HF other apps' spaces | about 88 MB | candidates |
| uv + pip caches | about 800 MB | regrow when installing |
