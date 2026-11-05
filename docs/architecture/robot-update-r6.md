# Robot update 1.10.0 -> 1.14.0 (R6, 2026-11-05)

Route: Reachy Mini Control, Settings, System Updates (Pollen's documented way). Control app itself stays at 0.9.34 on purpose.
No official rollback exists (only reflashing the ISO), so a backup came first.

## Before
- Backup `~/backups/pre-R6-20261105-1712.tar.gz` (77 MB, mode 600, contains Signal keys, so private): console DB (consistent copy), console secret + TLS, Signal data (`~/.local/share/signal-api`, container stopped a few seconds), swap drop-in, startup-app setting. Copied to the PC, SHA256 matched.
- Power: no battery sensor visible, adapter plugged in.

## After (all checked)
- daemon/SDK 1.14.0; `/venvs/apps_venv` synced to 1.14.0 by itself.
- Daemon active, control loop about 50 Hz, no daemon errors since boot.
- Startup app still off. Signal healthy. Disk 3.2 GB free. Swap drop-in survived (file 512 MiB).
- `reachyminios_check` identical before and after: audio recording, camera capture and motor ping fail with "busy" because the running daemon holds the devices; "Image validation FAILED" is unexplained. Nothing new.

## Open
- Control stopping apps after about 62 s: retest with the real app in R1 (acceptance: stays running more than 5 min with Control open).
- Delete the backup on the robot after a few stable days (keep the PC copy private).
