#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path


DEFAULT_ROOT = Path("/srv/zipterior/media/temp")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--older-than-hours", type=int, default=24)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    allowed_root = Path("/srv/zipterior/media/temp").resolve()
    if root != allowed_root:
        raise SystemExit(f"안전을 위해 {allowed_root} 경로만 정리할 수 있습니다.")
    root.mkdir(parents=True, exist_ok=True)

    cutoff = time.time() - max(1, args.older_than_hours) * 3600
    candidates = [p for p in root.rglob("*") if p.is_file() and p.stat().st_mtime < cutoff]
    total_bytes = sum(p.stat().st_size for p in candidates)

    if args.apply:
        for path in candidates:
            path.unlink(missing_ok=True)

    print(f"TEMP_MEDIA_FILES={len(candidates)}")
    print(f"TEMP_MEDIA_BYTES={total_bytes}")
    print("TEMP_MEDIA_MODE=" + ("APPLY" if args.apply else "DRY_RUN"))
    print("TEMP_MEDIA_CLEANUP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
