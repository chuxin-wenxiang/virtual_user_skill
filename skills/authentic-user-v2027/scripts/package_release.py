#!/usr/bin/env python3
"""Build a public-only installable ZIP with checksum, after release checks pass."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from check_release import PUBLIC_FILES, ROOT, check_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = check_release()
    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    version = (ROOT / "VERSION").read_text().strip()
    destination = Path(args.output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"authentic-user-v2027-{version}.zip"
    checksum = archive.with_suffix(".zip.sha256")
    if archive.exists() or checksum.exists():
        parser.error("Release output already exists; choose another directory")
    # Enumerate the reviewed allowlist, never recursively zip local archives or outputs.
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as handle:
        for name in sorted(PUBLIC_FILES):
            info = zipfile.ZipInfo(f"authentic-user-v2027/{name}", (2026, 10, 26, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            handle.writestr(info, (ROOT / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), "sha256": digest, "files": len(PUBLIC_FILES)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
