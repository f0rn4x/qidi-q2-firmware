#!/usr/bin/env python3
"""Inflate the embedded Klipper data dictionary from QIDI MCU firmware blobs.

Each QD_Q2_MCU / QD_Q2_THR / QD_Q2_BOX file is a raw ARM Cortex-M image that carries a
zlib-compressed Klipper *data dictionary* (JSON: version, build_versions, commands,
config, enumerations, ...). This scans a blob for zlib streams, inflates the largest one
that looks like a Klipper dictionary, and writes it next to the blob as <blob>.dict.json,
pretty-printed (2-space indent) for readability. If the inflated bytes can't be parsed as
JSON they are written verbatim instead.

Generic across firmware versions: it inspects whatever blobs it is pointed at and never
hard-codes file names or versions.

Usage:
    python fw_dict.py [TARGET ...]

TARGET may be a firmware blob file, or a directory (every file in it that is not JSON /
text is treated as a candidate). With no argument it defaults to the sibling `package`
directory (../package relative to this script) -- i.e. the matching <ver>-full extract.
"""
import json
import os
import re
import sys
import zlib

ZLIB_CMF  = 0x78                      # zlib header, 32K window, deflate
ZLIB_FLG  = (0x01, 0x9c, 0xda)        # common FLG bytes (no / default / best compression)
MAX_BYTES = 16_000_000               # generous cap; real dictionaries are well under 1 MB
SKIP_EXT  = (".json", ".txt", ".md")  # manifests, notes, and our own *.dict.json output


def find_zlib_streams(data):
    """Return [(offset, inflated_bytes), ...] for every inflatable zlib stream."""
    out = []
    for i in range(len(data) - 1):
        if data[i] == ZLIB_CMF and data[i + 1] in ZLIB_FLG:
            try:
                blob = zlib.decompressobj().decompress(data[i:], MAX_BYTES)
            except zlib.error:
                continue
            if len(blob) > 80:
                out.append((i, blob))
    return out


def looks_like_klipper_dict(blob):
    return b'"commands"' in blob or b'"config"' in blob or b'"version"' in blob


def field(blob, key):
    m = re.search(b'"' + key + b'"\\s*:\\s*"([^"]+)"', blob)
    return m.group(1).decode("ascii", "replace") if m else None


def candidates(target):
    if os.path.isdir(target):
        for name in sorted(os.listdir(target)):
            p = os.path.join(target, name)
            if os.path.isfile(p) and not name.lower().endswith(SKIP_EXT):
                yield p
    elif os.path.isfile(target):
        yield target
    else:
        print("  (not found: %s)" % target)


def write_dict(path, blob):
    """Write <blob>.dict.json pretty-printed; fall back to raw bytes if it won't parse."""
    out = path + ".dict.json"
    try:
        obj, _ = json.JSONDecoder().raw_decode(blob.decode("utf-8", "replace").lstrip())
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return out, True
    except ValueError:
        open(out, "wb").write(blob)
        return out, False


def process(path):
    data = open(path, "rb").read()
    streams = [s for s in find_zlib_streams(data) if looks_like_klipper_dict(s[1])]
    name = os.path.basename(path)
    if not streams:
        print("  %-16s no Klipper dictionary found" % name)
        return
    off, blob = max(streams, key=lambda s: len(s[1]))
    out, pretty = write_dict(path, blob)
    ver = field(blob, b"version")
    tag = "pretty" if pretty else "raw (unparseable)"
    print("  %-16s version=%-22s %6d-byte dict @0x%05x -> %s [%s]"
          % (name, ver, len(blob), off, os.path.basename(out), tag))


def main(argv):
    targets = argv[1:]
    if not targets:
        here = os.path.dirname(os.path.abspath(__file__))
        targets = [os.path.normpath(os.path.join(here, "..", "package"))]
    for t in targets:
        print("== %s ==" % t)
        for path in candidates(t):
            process(path)


if __name__ == "__main__":
    main(sys.argv)
