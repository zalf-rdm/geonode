#!/usr/bin/env python3
"""Find statically bundled copies of a C library inside installed Python wheels.

Neither pip-audit nor an image scanner can see these. pip-audit reports Python distributions and
Trivy reports apt packages; a wheel that vendors its own shared object -- as Pillow does with
libbrotlidec and its own FreeType -- falls between the two. CVE-2026-111497 (HTTP2Shell) lives in
exactly that gap, which is why this exists.

The default looks for the Brotli decoder and reports whether each copy carries the fix. The fix
(google/brotli 0ed4268) adds a BLOCK_SWITCH error code, so the marker is present in patched builds
and absent in affected ones -- the bundled version string stays 1.2.0 either way and proves nothing.

Usage:
    python3 security/scan_bundled_libs.py
    python3 security/scan_bundled_libs.py --symbol SSL_CTX_new --marker ''
"""

import argparse
import os
import site
import sys
import sysconfig


def site_dirs():
    dirs = set()
    if hasattr(site, "getsitepackages"):
        dirs.update(site.getsitepackages())
    for key in ("purelib", "platlib"):
        dirs.add(sysconfig.get_paths()[key])
    return sorted(d for d in dirs if os.path.isdir(d))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BrotliDecoderDecompress", help="symbol that identifies the bundled library")
    parser.add_argument("--marker", default="BLOCK_SWITCH", help="string present only in fixed builds; empty to skip the verdict")
    parser.add_argument("--paths", nargs="*", help="directories to scan (default: this interpreter's site-packages)")
    args = parser.parse_args()

    roots = args.paths or site_dirs()
    print("scanning:", ", ".join(roots))

    symbol = args.symbol.encode()
    marker = args.marker.encode() if args.marker else None
    affected = []

    for base in roots:
        for dirpath, _, filenames in os.walk(base):
            for name in filenames:
                if ".so" not in name:
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, "rb") as handle:
                        data = handle.read()
                except OSError:
                    continue
                if symbol not in data:
                    continue
                if marker is None:
                    print(f"  BUNDLED   {path}")
                elif marker in data:
                    print(f"  FIXED     {path}")
                else:
                    print(f"  AFFECTED  {path}")
                    affected.append(path)

    if not affected:
        print(f"no bundled copy of {args.symbol} without {args.marker or 'a marker'} found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
