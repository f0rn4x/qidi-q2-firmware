#!/usr/bin/env python3
"""Split a full firmware extract into a lean git tree + one binary bundle (release asset).

Run this AFTER copying a full extract (rootfs/ control/ package/ ...) into the repo
working tree. It:

  1. classifies every payload file as KEEP (stays in git) or ASSET (large / binary),
  2. writes the ASSET files into  dist/<name>.zip  (deflate level 9) at their
     repo-relative paths,
  3. records every ASSET file (path, size, sha256) plus the bundle's own
     name/size/sha256/url in  assets-manifest.json,
  4. removes the ASSET files from the working tree and prunes the emptied dirs.

Then commit the lean tree + manifest, tag the version, and upload dist/<name>.zip as
the release asset. `rehydrate.py` reverses this and verifies every hash.

A file is an ASSET if ANY of:
  - it lives in a vendored runtime tree (algo_app, fluidd, klippy-env, moonraker-env), or
  - its content is binary (NUL byte / not valid UTF-8 / ELF), or
  - it is >= the size threshold (default 1 MiB).
...except package/ and control/ (small, central reference) which always stay in git.
The binary/size tests are content-based, so renamed/moved binaries are caught
automatically (no per-version path patching).

Usage:
    python scripts/split-assets.py --version 1.1.0 --repo-slug you/qidi-q2-firmware
    python scripts/split-assets.py --version 1.1.0 --dry-run        # classify only
"""
import argparse
import hashlib
import json
import os
import sys
import zipfile

VENDOR   = ("/algo_app/", "/fluidd/", "/klippy-env/", "/moonraker-env/")
KEEP_TOP = ("package", "control", "scripts")
META     = {"README.md", ".gitattributes", ".gitignore", "assets-manifest.json"}
SKIP_DIR = {".git", "__pycache__", "dist"}


def is_binary(path):
    try:
        c = open(path, "rb").read(8192)
    except OSError:
        return True
    if not c:
        return False
    if c[:4] == b"\x7fELF" or b"\x00" in c:
        return True
    try:
        c.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(rel, full, threshold):
    top = rel.split("/", 1)[0]
    if top in KEEP_TOP or rel in META:
        return "keep"
    if any(v in "/" + rel for v in VENDOR):
        return "asset"
    if is_binary(full):
        return "asset"
    try:
        if os.path.getsize(full) >= threshold:
            return "asset"
    except OSError:
        pass
    return "keep"


def walk_payload(repo):
    for dp, dns, fns in os.walk(repo):
        dns[:] = [d for d in dns if d not in SKIP_DIR]
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, repo).replace("\\", "/")
            if rel.split("/", 1)[0] == "dist":
                continue
            yield rel, full


def human(n):
    return "%.1f MB" % (n / 1048576)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--repo-slug", default=None, help="owner/name, used to build the asset URL")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--threshold", type=int, default=1048576, help="size cutoff in bytes (default 1 MiB)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv[1:])

    repo = os.path.abspath(a.repo)
    assets, keep = [], []
    for rel, full in walk_payload(repo):
        bucket = assets if classify(rel, full, a.threshold) == "asset" else keep
        bucket.append((rel, full))

    a_bytes = sum(os.path.getsize(f) for _, f in assets)
    k_bytes = sum(os.path.getsize(f) for _, f in keep)
    print("repo            : %s" % repo)
    print("ASSET (-> bundle): %5d files, %s" % (len(assets), human(a_bytes)))
    print("KEEP  (-> git)   : %5d files, %s" % (len(keep), human(k_bytes)))
    if a.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    dist = os.path.join(repo, "dist")
    os.makedirs(dist, exist_ok=True)
    bundle_name = "qidi-q2-%s-assets.zip" % a.version
    bundle = os.path.join(dist, bundle_name)

    print("\nwriting %s (deflate -9) ..." % bundle_name)
    files = []
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, full in sorted(assets):
            files.append({"path": rel, "bytes": os.path.getsize(full), "sha256": sha256(full)})
            zf.write(full, arcname=rel)

    bundle_sz = os.path.getsize(bundle)
    url = None
    if a.repo_slug:
        url = "https://github.com/%s/releases/download/v%s/%s" % (a.repo_slug, a.version, bundle_name)
    manifest = {
        "version": a.version,
        "tag": "v%s" % a.version,
        "asset": {"file": bundle_name, "bytes": bundle_sz, "sha256": sha256(bundle), "url": url},
        "files": files,
        "summary": {"count": len(files), "bytes": a_bytes},
    }
    with open(os.path.join(repo, "assets-manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    # remove asset files from the working tree, then prune the dirs they emptied
    for _, full in assets:
        os.remove(full)
    for d in sorted({os.path.dirname(f) for _, f in assets}, key=len, reverse=True):
        cur = d
        while cur and cur != repo and os.path.isdir(cur) and not os.listdir(cur):
            os.rmdir(cur)
            cur = os.path.dirname(cur)

    ratio = 100 * bundle_sz / max(a_bytes, 1)
    print("bundle          : dist/%s  (%s, %.0f%% of raw)" % (bundle_name, human(bundle_sz), ratio))
    print("manifest        : assets-manifest.json  (%d files)" % len(files))
    if not url:
        print("NOTE: no --repo-slug; asset.url left null. Set it before publishing, or "
              "rehydrate with --asset.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
