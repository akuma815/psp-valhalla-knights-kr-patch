from __future__ import annotations

import csv
import hashlib
import os
import shutil
from pathlib import Path

from in_place_patcher import parse_res_header


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
PATCH_ROOT = WORKSPACE / "r02_battle_ui_extracted" / "textures"
GLOBAL_PATH = ROOT / "PSP_GAME" / "USRDIR" / "Resource" / "global" / "global.res"
BACKUP_PATH = WORKSPACE / "backups" / "r02_station_before_patch" / "global.res"
MANIFEST_PATH = WORKSPACE / "r02_battle_ui_extracted" / "apply_manifest.csv"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    if not GLOBAL_PATH.exists():
        raise FileNotFoundError(GLOBAL_PATH)

    before = GLOBAL_PATH.read_bytes()
    records = {record["name"]: record for record in parse_res_header(before)}
    patch_names = ("station0", "station2")
    for name in patch_names:
        if name not in records:
            raise KeyError(f"global.res record not found: {name}")

    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP_PATH.exists():
        shutil.copy2(GLOBAL_PATH, BACKUP_PATH)

    after = bytearray(before)
    manifest = []
    changed_ranges = []
    for name in patch_names:
        record = records[name]
        patch_path = PATCH_ROOT / f"{name}_korean.gim"
        patch = patch_path.read_bytes()
        if len(patch) != record["size"]:
            raise ValueError(
                f"{name}: patch size {len(patch)} != record size {record['size']}"
            )
        start = record["offset"]
        end = start + record["size"]
        old_record = before[start:end]
        after[start:end] = patch
        changed_ranges.append((start, end))
        manifest.append(
            {
                "Record": name,
                "Offset": f"0x{start:X}",
                "Size": record["size"],
                "Before SHA256": sha256(old_record),
                "After SHA256": sha256(patch),
                "Patch File": str(patch_path.relative_to(ROOT)),
            }
        )

    for index, (old_byte, new_byte) in enumerate(zip(before, after)):
        if old_byte == new_byte:
            continue
        if not any(start <= index < end for start, end in changed_ranges):
            raise RuntimeError(f"byte outside station records changed at {index:#x}")

    temp_path = GLOBAL_PATH.with_suffix(".res.r02.tmp")
    temp_path.write_bytes(after)
    os.replace(temp_path, GLOBAL_PATH)
    installed = GLOBAL_PATH.read_bytes()
    if installed != bytes(after):
        raise RuntimeError("installed global.res verification failed")

    fields = [
        "Record", "Offset", "Size", "Before SHA256", "After SHA256", "Patch File"
    ]
    with MANIFEST_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)

    print(f"Backup: {BACKUP_PATH}")
    print(f"Before global SHA256: {sha256(before)}")
    print(f"After global SHA256:  {sha256(installed)}")
    for row in manifest:
        print(f"Patched {row['Record']} at {row['Offset']} ({row['Size']} bytes)")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
