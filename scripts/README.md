# Firmware extraction scripts

The code that produced these `*-full` extracts, made generic so it works across current
and future QIDI Q2 firmware packages. Nothing is hard-coded to a version — names,
nesting (`QD_Update/`), and `.tar` compression are all detected at runtime.

All paths are resolved **relative to the `firmware-extract` folder** (this script's
grandparent), so the tree can be moved without breaking anything and the generated
`rootfs-extract.log` carries `.\firmware-extract\...` paths rather than an absolute root.

## Requirements

- Windows `tar.exe` (bsdtar / libarchive — ships with Windows 10/11)
- Python 3 on `PATH`

## Files

| File | What it does |
|---|---|
| `extract-firmware.ps1` | End-to-end unpack of a firmware `.zip` into `<ver>/` (intermediates) and `<ver>-full/` (the extract: `control/`, `rootfs/`, `package/`, `rootfs-extract.log`). |
| `fw_dict.py` | Inflates the embedded Klipper data dictionary from each MCU blob and writes it **pretty-printed** to `package/<blob>.dict.json`. Called automatically by the `.ps1`; also runnable on its own. |
| `split-assets.py` | Splits a full extract into a lean git tree + one binary `dist/*.zip` bundle (deflate -9) + `assets-manifest.json`. Run before committing each version. |
| `rehydrate.py` | The reverse: downloads/verifies the release bundle named in `assets-manifest.json` and overlays it onto the tree, checking every file's sha256. |

## Usage

From this `scripts/` folder (PowerShell):

```powershell
# Re-create the 1.1.0 extract (version parsed from the zip name)
.\extract-firmware.ps1 -Zip 'C:\path\to\Q2_V1.1.0.zip'

# A future package, with an explicit version label
.\extract-firmware.ps1 -Zip '..\..\QD_Q2-v1.1.3.zip' -Version 1.1.3
```

Inflate dictionaries by hand (e.g. after copying blobs in yourself):

```powershell
python .\fw_dict.py ..\package          # a directory of blobs
python .\fw_dict.py ..\package\QD_Q2_MCU # a single blob
```

## What `extract-firmware.ps1` does

1. Find the SOC blob in the zip (`*QD_Q2_SOC*`) and extract it — it is a Debian package
   (`ar`: `debian-binary` + `control.tar.*` + `data.tar.*`).
2. Split the `.deb` into its `control.tar.*` / `data.tar.*` members.
3. Extract `control.tar.*` → `control/` and `data.tar.*` → `rootfs/`. The rootfs
   extraction's warnings (Windows can't create the Linux symlinks) are written to
   `rootfs-extract.log` with the Windows root rewritten to `.`.
4. Copy every non-SOC zip member (`QD_Q2_MCU` / `_THR` / `_BOX`,
   `firmware_manifest.json`, …) into `package/` by leaf name.
5. Run `fw_dict.py` over `package/` to inflate **and pretty-print** each MCU dictionary.

## Releasing binaries as assets (no Git LFS)

The heavy payload (Qt/OpenCV/ONNX `.so`, model weights, Fluidd's bundled UI, ELF
binaries) is kept **out of git** and shipped as one zip per release, so the repo stays a
few MB of diffable text. `assets-manifest.json` is the link between the two.

A file is bundled as an **asset** if it is in a vendored runtime tree
(`**/algo_app/**`, `**/fluidd/**`), is binary, or is ≥ 1 MiB — except `package/` and
`control/`, which always stay in git. The binary/size tests are content-based, so a
renamed/moved binary (e.g. `client` → `qidiclient`) is caught automatically.

**Publish a version** (fits the copy-over-and-tag flow):

```powershell
# 1. clear the old payload, copy the new full extract in (keep .git, scripts, .gitattributes)
Remove-Item -Recurse -Force rootfs, control, package, rootfs-extract.log
#    ...copy <ver>-full\{rootfs,control,package,rootfs-extract.log} + README.md in...

# 2. split: writes dist\qidi-q2-<ver>-assets.zip + assets-manifest.json, prunes binaries
python scripts\split-assets.py --version 1.1.0 --repo-slug you/qidi-q2-firmware

# 3. commit the lean tree + manifest, tag, and upload the bundle to the release
git add -A
git commit -m "firmware 1.1.0"
git tag -a v1.1.0 -m "QIDI Q2 firmware 1.1.0"
gh release create v1.1.0 dist\qidi-q2-1.1.0-assets.zip   # or upload via the web UI
```

**Reconstruct a version** (consumer, after `git clone` + checkout of a tag):

```powershell
python scripts\rehydrate.py            # downloads the bundle from the manifest, verifies, overlays
python scripts\rehydrate.py --asset dist\qidi-q2-1.1.0-assets.zip   # or use a local bundle
```

`dist/` is git-ignored. See `../README.md` for the per-version extract details.
