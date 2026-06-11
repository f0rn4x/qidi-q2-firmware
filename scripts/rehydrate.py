#!/usr/bin/env python3
"""Reconstruct the full firmware extract from the lean git tree + the release bundle.

Downloads (or uses a local) binary bundle named in assets-manifest.json, verifies its
sha256, overlays it onto the working tree, then checks every restored file against the
manifest's per-file size + sha256.

Usage:
    python scripts/rehydrate.py                                  # download from manifest url
    python scripts/rehydrate.py --asset dist/qidi-q2-1.1.0-assets.zip   # use a local bundle
    python scripts/rehydrate.py --no-verify                      # presence only (skip hashing)

Only the Python standard library is required.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request
import zipfile


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    print("downloading %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "qidi-q2-firmware-rehydrate"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if total:
                sys.stdout.write("\r  %5.1f%%  (%.0f / %.0f MB)"
                                 % (100 * got / total, got / 1048576, total / 1048576))
                sys.stdout.flush()
        sys.stdout.write("\n")


def safe_extract(zf, repo):
    root = os.path.realpath(repo)
    for m in zf.infolist():
        dest = os.path.realpath(os.path.join(repo, m.filename))
        if dest != root and not dest.startswith(root + os.sep):
            raise SystemExit("refusing unsafe path in bundle: %s" % m.filename)
    zf.extractall(repo)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--asset", default=None, help="local bundle .zip (skip download)")
    ap.add_argument("--no-verify", action="store_true", help="check presence only, skip hashing")
    ap.add_argument("--keep-bundle", action="store_true", help="keep a downloaded bundle afterwards")
    a = ap.parse_args(argv[1:])

    repo = os.path.abspath(a.repo)
    mpath = a.manifest or os.path.join(repo, "assets-manifest.json")
    with open(mpath, encoding="utf-8") as f:
        man = json.load(f)
    asset = man["asset"]

    bundle = a.asset
    downloaded = False
    if not bundle:
        local = os.path.join(repo, "dist", asset["file"])
        if os.path.isfile(local):
            bundle = local
        elif asset.get("url"):
            os.makedirs(os.path.join(repo, "dist"), exist_ok=True)
            bundle = local
            download(asset["url"], bundle)
            downloaded = True
        else:
            raise SystemExit("no --asset, no dist/%s, and the manifest has no url" % asset["file"])

    if asset.get("sha256"):
        print("verifying bundle sha256 ...")
        got = sha256(bundle)
        if got != asset["sha256"]:
            raise SystemExit("bundle sha256 mismatch:\n  expected %s\n  got      %s"
                             % (asset["sha256"], got))
        print("  ok")

    print("extracting %d files over %s ..." % (man["summary"]["count"], repo))
    with zipfile.ZipFile(bundle) as zf:
        safe_extract(zf, repo)

    missing, bad = [], []
    for e in man["files"]:
        p = os.path.join(repo, e["path"].replace("/", os.sep))
        if not os.path.isfile(p):
            missing.append(e["path"])
            continue
        if not a.no_verify:
            if os.path.getsize(p) != e["bytes"] or sha256(p) != e["sha256"]:
                bad.append(e["path"])

    if missing or bad:
        print("FAILED: %d missing, %d corrupt" % (len(missing), len(bad)))
        for x in (missing + bad)[:20]:
            print("  - %s" % x)
        return 1

    tail = "" if not a.no_verify else " (presence only)"
    print("OK: %d files restored and verified%s." % (len(man["files"]), tail))
    if downloaded and not a.keep_bundle:
        os.remove(bundle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
