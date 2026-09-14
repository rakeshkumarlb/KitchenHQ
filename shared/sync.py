#!/usr/bin/env python3
"""Vendor shared/*.py modules into the services that cannot import them directly.

KitchenHQ's three services each build from their own Docker context and share no
package, so each module in SOURCE_FILES (shared/constants.py, shared/tags.py) is copied
verbatim into each Python service that needs it. This script is the copier.

Usage:
  python shared/sync.py            # write / refresh the vendored copies
  python shared/sync.py --check    # exit 1 if any copy is missing or has drifted

Comparison and writes are byte-exact (LF), so a copy that differs only by line
endings is still reported and rewritten.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "shared"
SOURCE_FILES = ("constants.py", "tags.py")
TARGET_DIRS = (
    ROOT / "dbmcp",
    ROOT / "agents" / "app",
)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale: list[Path] = []
    for filename in SOURCE_FILES:
        source_bytes = (SOURCE_DIR / filename).read_bytes()
        for target_dir in TARGET_DIRS:
            target = target_dir / filename
            current = target.read_bytes() if target.exists() else None
            if current == source_bytes:
                continue
            stale.append(target)
            if not check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source_bytes)
                print(f"wrote {target.relative_to(ROOT)}")

    if check and stale:
        for target in stale:
            print(f"STALE: {target.relative_to(ROOT)} differs from its shared/ source", file=sys.stderr)
        print("run `python shared/sync.py` to refresh", file=sys.stderr)
        return 1
    if check:
        print("vendored copies are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
