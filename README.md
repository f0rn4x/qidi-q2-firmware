# QIDI Q2 firmware 1.1.2 — full extract

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

This repository is a **full unpack of the QIDI Q2 v1.1.2 firmware update package**,
produced on Windows with `tar.exe` (bsdtar / libarchive) and Python.

- **Source:** `QD_Q2-v1.1.2.zip` (228.6 MB, 239,657,027 bytes)
  - MD5 `23055d00af73ac3d081a435fab308701`
  - SHA-256 `ee9010a4aafb7ab6fab0c6f7843b6b064c7e490e8a8dc1aa542d211d5f6ea31e`
- **SOC version:** `01.01.02.01` (built 2026-06-01, region NA)
- Extracted: 2026-06-10

## Contents

| Path | What |
|---|---|
| `rootfs/` | the SOC application payload from `data.tar.xz` — `etc/ home/qidi/ root/ tmp/ usr/` (klipper, klippy-env, fluidd, moonraker, `usr/local/bin/algo_app` — see below). **7882 files, 0.86 GB.** |
| `control/` | the `.deb` package metadata (`control.tar.xz`): `control`, maintainer scripts |
| `package/` | the non-SOC update members copied straight from the zip: `firmware_manifest.json`, `QD_Q2_MCU`, `QD_Q2_THR`, `QD_Q2_BOX` |
| `package/*.dict.json` | the inflated, pretty-printed Klipper data dictionaries from each MCU blob (see below) |
| `rootfs-extract.log` | bsdtar messages from the rootfs extraction (symlink/ownership warnings) |
| `scripts/` | extraction + asset tooling (`extract-firmware.ps1`, `fw_dict.py`, `split-assets.py`, `rehydrate.py`) — see `scripts/README.md` |
| `assets-manifest.json` | links this tree to the binary bundle attached to the release (consumed by `scripts/rehydrate.py`) |

## How it was extracted

The SOC blob (`QD_Q2_SOC_01.01.02.01_20260601_Release_NA`) is a **Debian package**
(an `ar` archive: `debian-binary` + `control.tar.xz` + `data.tar.xz`). `data.tar.xz`
is the root filesystem overlay.

```powershell
$zip  = "<path-to>\QD_Q2-v1.1.2.zip"
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

# 4. copy the MCU/THR/BOX firmware blobs + manifest out of the zip (non-SOC entries)
#    -> $full\package\
```

A generic, reusable version of these steps (handles current and future firmware
packages) lives in `scripts/` — see `scripts/README.md`.

The MCU/THR/BOX files are **not archives** — they are raw ARM Cortex-M firmware images
(vector table at offset 0: initial SP + reset handler in flash `0x08000000`). Their
embedded **zlib-compressed Klipper data dictionary** was inflated by `scripts/fw_dict.py`
and written (pretty-printed) as `package/QD_Q2_*.dict.json`.

## Embedded MCU firmware versions

| Blob | `version` (from its dictionary) | matches `firmware_manifest.json`? |
|---|---|---|
| `QD_Q2_MCU` | `02.01.01.09` | yes (MCU `02.01.01.09`) |
| `QD_Q2_THR` | `02.02.01.08` | yes (THR `02.02.01.08`) |
| `QD_Q2_BOX` | `KLP_MCU_MKS_V2_1.1.3` | manifest lists BOX `02.03.01.13` |

All three are **Klipper** MCU firmware (GPLv3), built with GNU Arm Embedded Toolchain
10.3-2021.10. Each dictionary also holds the full command/response/config/pin map.

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

## Other bundled binaries

- `home/qidi/QIDI_Client/bin/qidiclient` (~86 MB) — QIDI's proprietary printer client.
- `root/Frp_bak/frpc` (~12 MB) — the **FRP (Fast Reverse Proxy) client** QIDI bundles
  for remote / cloud printer access (open source, Apache-2.0).

> Heads-up: antivirus commonly flags `frpc` as a **PUA / hacktool**. `frp` is a
> legitimate tunneling tool that malware also abuses, so it trips generic heuristics —
> this is the stock vendor binary, not injected malware. It rides in the release
> bundle, so expect your AV (and downloaders') to warn on it.

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
- **FRP** (`root/Frp_bak/frpc`) — the bundled reverse-proxy client, Apache-2.0.
- **QIDI's proprietary binaries** — the `algo_app` CV application (`main`), the
  `qidiclient` printer client, and the encrypted model weights (`algo.enc`,
  `algo_pf.enc`) are **© QIDI Technology**, included only as the firmware ships them.
  This repository grants no license to use or redistribute them.

Only the firmware-extraction tooling (`extract-firmware.ps1` / `fw_dict.py`) is
original work.

See `scripts/README.md` for the extraction + asset-bundling method.
