# QIDI Q2 firmware 1.1.1 — full extract

> **Unofficial archive.** A community unpack of QIDI's stock Q2 firmware, kept for
> reference, research, and repair. **Not affiliated with or endorsed by QIDI
> Technology.** All contents belong to their respective owners under their original
> licenses (see [Licensing](#licensing)); a rights holder who wants something removed
> can open an issue.
>
> **Binaries live in the release, not in git.** This repo holds only the lean text tree
> plus `assets-manifest.json`. To reconstruct the full extract, clone it and run
> `python scripts/rehydrate.py` — it downloads this version's bundle from the matching
> GitHub release, verifies it, overlays it, and checks every file against the manifest.

This repository is a **full unpack of the QIDI Q2 v1.1.1 firmware update package**,
produced on Windows with `tar.exe` (bsdtar / libarchive) and Python.

- **Source:** `Q2_V1.1.1.zip` (137,130,401 bytes)
  - MD5 `add1a1c1b0dec6e0b91fc2c2384ccdd3`
  - SHA-256 `4c7d0f5b52d1a780f3e02b92bea6c7b751690c2b4da529eafd2ceb662241ecb7`
- **SOC version:** `V1.1.1` (built 2026-01-09)
- Extracted: 2026-06-10

> Note: the 1.1.1 package has **no `firmware_manifest.json` and no BOX firmware** —
> both were added in 1.1.2. The home dir here is `/home/mks/` (1.1.2 switched to
> `/home/qidi/`).

## Contents

| Path | What |
|---|---|
| `rootfs/` | the SOC application payload from `data.tar.xz` (klipper, klippy-env, fluidd, moonraker under `home/mks/`, plus QIDI's `algo_app` under `usr/local/bin/` — see below). **3086 files, 0.54 GB.** |
| `control/` | the `.deb` package metadata (`control.tar.xz`) |
| `package/` | the non-SOC update members copied from the zip: `QD_Q2_MCU`, `QD_Q2_THR` |
| `package/*.dict.json` | the inflated, pretty-printed Klipper data dictionaries from each MCU blob (see below) |
| `rootfs-extract.log` | bsdtar messages from the rootfs extraction (symlink/ownership warnings) |
| `scripts/` | extraction + asset tooling (`extract-firmware.ps1`, `fw_dict.py`, `split-assets.py`, `rehydrate.py`) — see `scripts/README.md` |
| `assets-manifest.json` | links this tree to the binary bundle attached to the release (consumed by `scripts/rehydrate.py`) |

## How it was extracted

The SOC blob (`QD_Q2_SOC_V1.1.1_20260109_Release`) is a **Debian package** (an `ar`
archive: `debian-binary` + `control.tar.xz` + `data.tar.xz`). `data.tar.xz` is the
root filesystem overlay.

```powershell
$zip  = "<path-to>\Q2_V1.1.1.zip"
$work = ".\work"                            # scratch for the .deb + *.tar.xz
$full = "."                                 # the extract — this repo's root

# 1. pull the SOC .deb out of the zip
Add-Type -AssemblyName System.IO.Compression.FileSystem
$a = [System.IO.Compression.ZipFile]::OpenRead($zip)
$e = $a.Entries | Where-Object { $_.FullName -like 'QD_Q2_SOC*' }
[System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, "$work\QD_Q2_SOC.deb", $true)
$a.Dispose()

# 2. .deb -> its tar members
tar.exe -xf "$work\QD_Q2_SOC.deb" -C $work control.tar.xz data.tar.xz

# 3. full extract: package metadata + the entire rootfs overlay
tar.exe -xf "$work\control.tar.xz" -C "$full\control"
tar.exe -xf "$work\data.tar.xz"    -C "$full\rootfs"

# 4. copy the MCU/THR firmware blobs out of the zip (non-SOC entries)
#    -> $full\package\
```

A generic, reusable version of these steps (handles current and future firmware
packages) lives in `scripts/` — see `scripts/README.md`.

The MCU/THR files are **not archives** — they are raw ARM Cortex-M firmware images
(vector table at offset 0: initial SP + reset handler in flash `0x08000000`). Their
embedded **zlib-compressed Klipper data dictionary** was inflated with
`scripts/fw_dict.py` and written (pretty-printed) as `package/QD_Q2_*.dict.json`.

## Embedded MCU firmware versions

| Blob | `version` (from its dictionary) |
|---|---|
| `QD_Q2_MCU` | `KLP_MCU_MAIN_V2_1.0.4` |
| `QD_Q2_THR` | `KLP_MCU_THR_V2_1.0.5` |

Both are **Klipper** MCU firmware (GPLv3), built with GNU Arm Embedded Toolchain
10.3-2021.10. They are **identical to 1.1.0** (same versions *and* byte sizes) — the
MCU/THR firmware was unchanged from 1.1.0 to 1.1.1; only the SOC payload differs.
(1.1.1 uses the `KLP_MCU_*_V2_1.0.x` naming scheme; 1.1.2 switched the MCU/THR to
numeric `02.0x.0x.xx` versions matching its manifest.)

## The `algo_app` service (QIDI's AI print monitor)

`rootfs/usr/local/bin/algo_app/` is QIDI's on-device **computer-vision / AI
print-monitoring** daemon — the name is short for *algorithm application*. It is a
PyInstaller-frozen Python app bundling **OpenCV (`cv2`), ONNX Runtime, NumPy and
Qt5**, run by the `algo_app.service` systemd unit (`ExecStart=.../main`, started after
`moonraker.service`, pinned to one core with `Nice=19` / `MemoryMax=250M`).

From `configs/config.xml`, it:

- ingests a **video stream** (camera / network) — or a video file for testing;
- runs **per-frame inference/detection** as printing proceeds (with a
  `min_occluded_frame` option to pick the frame where the print head least blocks the
  view);
- saves both **raw** and **post-detection** video, plus the best frame per layer, to
  `/home/qidi/video`;
- exposes its own API on port **9010** and talks to Moonraker on **7125**.

The detection models are the **encrypted** weights `weights/algo.enc` (~42 MB) and
`weights/algo_pf.enc` (~5.5 MB). The three `*.onnx` files under `_internal/`
(`logreg_iris`, `mul_1`, `sigmoid`) are ONNX Runtime's own bundled **unit-test
fixtures**, *not* QIDI models.

> Heads-up: `configs/config.xml` ships a cleartext **default management credential**
> (`qidi` / `qiditech`). It is a factory default present on every Q2 — not a
> per-machine secret — but it is included in this archive.

## Caveats (Windows)

- Symlinks and Linux ownership/permissions are **not** preserved (bsdtar warns and
  exits non-zero — see `rootfs-extract.log`); all regular files extracted fine.
- `data.tar.xz` is the QIDI **overlay** payload, not a complete Debian base OS.

## Licensing

This is an unofficial archive that bundles third-party software, each under its own
license:

- **Klipper** (MCU firmware + `klippy`) — GPLv3.
- **Moonraker** and **Fluidd** — GPLv3 / their respective open-source licenses.
- The vendored Python / Qt / OpenCV / NumPy / ONNX Runtime under
  `rootfs/usr/local/bin/algo_app/_internal/` — their respective upstream licenses.
- **QIDI's `algo_app`** — the compiled CV application (`main`, `client`) and the
  encrypted model weights (`algo.enc`, `algo_pf.enc`) are **proprietary,
  © QIDI Technology**, included only as the firmware ships them. This repository
  grants no license to use or redistribute them.

Only the firmware-extraction tooling (`extract-firmware.ps1` / `fw_dict.py`) is
original work.

See `scripts/README.md` for the extraction + asset-bundling method.
