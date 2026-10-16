import csv
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

from extract_tsqv import parse_resc


MANIFEST_FIELDS = [
    "File Path",
    "Status",
    "Original Size",
    "Patched Size",
    "Original SHA256",
    "Patched SHA256",
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for block in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_files(root):
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }


def expected_modified_paths(workspace):
    expected = {
        "SYSDIR/BOOT.BIN",
        "SYSDIR/EBOOT.BIN",
        "USRDIR/Resource/global/global.res",
        "USRDIR/Resource/tbldata/tbldata.res",
    }
    scpack_manifest = workspace / "tsqv_rebuilt/scpack_manifest.csv"
    with scpack_manifest.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            parts = row["File Path"].replace("\\", "/").split("/")
            if len(parts) != 2 or parts[0] != "scpack":
                raise ValueError(f"invalid scpack manifest path: {row['File Path']!r}")
            expected.add(f"USRDIR/Resource/scpack/{parts[1]}")

    # EVSCRIPT choice/prompt strings live directly in scpack archives rather
    # than TSQV records.  Once their translation CSV is complete, every
    # archive listed by the occurrence manifest is an intentional build
    # target, including archives that contain no TSQV replacement.
    ev_translation = workspace / "evscript_text/evscript_translation.csv"
    ev_occurrences = workspace / "evscript_text/evscript_occurrences.csv"
    if ev_translation.exists() and ev_occurrences.exists():
        with ev_translation.open("r", encoding="utf-8-sig", newline="") as csv_file:
            translation_rows = list(csv.DictReader(csv_file))
        if translation_rows and all(
            row.get("Translated", "").strip() for row in translation_rows
        ):
            with ev_occurrences.open("r", encoding="utf-8-sig", newline="") as csv_file:
                for row in csv.DictReader(csv_file):
                    expected.add(f"USRDIR/Resource/scpack/{row['Archive']}")
    return expected


def run_step(script, project_root):
    print(f"\n=== Running {script.name} ===", flush=True)
    subprocess.run(
        [sys.executable, str(script)],
        cwd=project_root,
        check=True,
    )


def validate_integrated_sttv(project_root, workspace):
    tbldata_path = project_root / "PSP_GAME/USRDIR/Resource/tbldata/tbldata.res"
    tbldata = tbldata_path.read_bytes()
    records = {
        name.lower(): tbldata[offset : offset + size]
        for name, offset, size in parse_resc(tbldata)
    }
    manifest_path = workspace / "sttv_rebuild/manifest.csv"
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        manifest_rows = list(csv.DictReader(csv_file))
    if len(manifest_rows) != 17:
        raise RuntimeError(
            f"STTV manifest has {len(manifest_rows)} records; expected 17"
        )

    checked_strings = 0
    expanded_slots = 0
    for row in manifest_rows:
        record_name = row["Record Name"].lower()
        expected_path = workspace / "sttv_rebuild/records" / f"{record_name}.bin"
        expected = expected_path.read_bytes()
        actual = records.get(record_name)
        if actual is None:
            raise RuntimeError(f"integrated tbldata is missing {record_name}")
        if actual != expected:
            raise RuntimeError(
                f"integrated STTV does not match staged record: {record_name}"
            )
        if hashlib.sha256(actual).hexdigest() != row["Rebuilt SHA256"]:
            raise RuntimeError(f"integrated STTV hash mismatch: {record_name}")

        string_count, table_offset = struct.unpack_from("<II", actual, 8)
        if table_offset != 0x10 or string_count != int(row["String Count"]):
            raise RuntimeError(f"integrated STTV header mismatch: {record_name}")
        checked_strings += string_count
        expanded_slots += int(row["Expanded Original Slots"])

    if checked_strings != 1517:
        raise RuntimeError(
            f"integrated STTV coverage mismatch: "
            f"strings={checked_strings}"
        )
    print(
        f"Integrated STTV verified: {len(manifest_rows)} records, "
        f"{checked_strings} strings, {expanded_slots} expanded old slots, "
        "0 truncations."
    )


def validate_and_write_manifest(project_root, workspace):
    original_root = project_root / "Original/PSP_GAME"
    patched_root = project_root / "PSP_GAME"
    manifest_path = workspace / "integrated_build_manifest.csv"

    original_files = collect_files(original_root)
    patched_files = collect_files(patched_root)
    missing = set(original_files) - set(patched_files)
    extra = set(patched_files) - set(original_files)
    if missing or extra:
        raise RuntimeError(
            f"PSP_GAME structure mismatch: missing={len(missing)}, extra={len(extra)}"
        )

    manifest_rows = []
    actual_modified = set()
    for relative_path in sorted(original_files):
        original_path = original_files[relative_path]
        patched_path = patched_files[relative_path]
        original_hash = sha256(original_path)
        patched_hash = sha256(patched_path)
        status = "modified" if original_hash != patched_hash else "unchanged"
        if status == "modified":
            actual_modified.add(relative_path)
        manifest_rows.append(
            {
                "File Path": relative_path,
                "Status": status,
                "Original Size": original_path.stat().st_size,
                "Patched Size": patched_path.stat().st_size,
                "Original SHA256": original_hash,
                "Patched SHA256": patched_hash,
            }
        )

    expected_modified = expected_modified_paths(workspace)
    unexpected = actual_modified - expected_modified
    missing_changes = expected_modified - actual_modified
    if unexpected or missing_changes:
        raise RuntimeError(
            "integrated build change set mismatch: "
            f"unexpected={len(unexpected)}, missing={len(missing_changes)}"
        )

    with manifest_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\nIntegrated PSP_GAME files: {len(manifest_rows)}")
    print(f"Expected modified files: {len(expected_modified)}")
    print("Unexpected modified files: 0")
    print(f"Manifest: {manifest_path}")
    return manifest_path, actual_modified


def main():
    workspace = Path(__file__).resolve().parent
    project_root = workspace.parent

    # Every component builder starts from files under Original, so rerunning
    # this pipeline produces a clean, deterministic integrated resource set.
    run_step(workspace / "sync_missing_fixed_translations.py", project_root)
    run_step(workspace / "in_place_patcher.py", project_root)
    run_step(workspace / "patch_name_input.py", project_root)
    run_step(workspace / "render_r02_station_korean.py", project_root)
    run_step(workspace / "apply_r02_station_patch.py", project_root)
    run_step(workspace / "rebuild_fixed_name_tables.py", project_root)
    run_step(workspace / "rebuild_sttv_records.py", project_root)
    validate_integrated_sttv(project_root, workspace)
    run_step(workspace / "rebuild_tsqv_records.py", project_root)
    run_step(workspace / "repack_tsqv_scpack.py", project_root)
    run_step(workspace / "rebuild_evscript_text.py", project_root)
    validate_and_write_manifest(project_root, workspace)

    print("\n=== FULL TRANSLATION BUILD COMPLETED ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
