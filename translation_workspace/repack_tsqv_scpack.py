import csv
import hashlib
import struct
import sys
from pathlib import Path

from extract_tsqv import parse_resc
from rebuild_tsqv_records import parse_tsqv_slots


MANIFEST_FIELDS = [
    "File Path",
    "Original Size",
    "Repacked Size",
    "Size Delta",
    "Replaced TSQV Records",
    "SHA256",
]


def align_up(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def read_rebuilt_manifest(path):
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    expected = {}
    for row in rows:
        parts = row["File Path"].replace("\\", "/").split("/")
        if len(parts) != 3 or parts[0] != "scpack":
            raise ValueError(f"invalid manifest path: {row['File Path']!r}")
        key = (parts[1], parts[2])
        if key in expected:
            raise ValueError(f"duplicate rebuilt record: {parts[1]}/{parts[2]}")
        expected[key] = row
    return expected


def repack_archive(original, pack_name, rebuilt_root, expected_records):
    if original[:4] != b"RESC":
        raise ValueError(f"{pack_name}: not a RESC archive")

    count = struct.unpack_from("<I", original, 4)[0]
    records = parse_resc(original)
    if len(records) != count:
        raise ValueError(f"{pack_name}: record count mismatch")
    if len({name for name, _, _ in records}) != len(records):
        raise ValueError(f"{pack_name}: duplicate record names")

    header_end = 8 + count * 16
    first_data_offset = align_up(header_end, 16)
    if records and records[0][1] != first_data_offset:
        raise ValueError(f"{pack_name}: unexpected first record alignment")
    if any(original[header_end:first_data_offset]):
        raise ValueError(f"{pack_name}: nonzero header padding")

    header = bytearray(original[:first_data_offset])
    output = bytearray(header)
    replaced = set()

    for record_index, (record_name, record_offset, record_size) in enumerate(records):
        aligned_offset = align_up(len(output), 16)
        output.extend(b"\x00" * (aligned_offset - len(output)))

        source_record = original[record_offset : record_offset + record_size]
        key = (pack_name, record_name)
        if key in expected_records:
            rebuilt_path = rebuilt_root / pack_name / f"{record_name}.bin"
            rebuilt_record = rebuilt_path.read_bytes()
            parse_tsqv_slots(rebuilt_record)
            expected_hash = expected_records[key]["SHA256"]
            actual_hash = hashlib.sha256(rebuilt_record).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(
                    f"{pack_name}/{record_name}: rebuilt SHA-256 mismatch"
                )
            record_data = rebuilt_record
            replaced.add(key)
        else:
            record_data = source_record

        entry_offset = 8 + record_index * 16
        # Preserve the original reversed 8-byte name field; update only size/offset.
        struct.pack_into("<II", header, entry_offset + 8, len(record_data), aligned_offset)
        output[entry_offset + 8 : entry_offset + 16] = header[
            entry_offset + 8 : entry_offset + 16
        ]
        output.extend(record_data)

    final_size = align_up(len(output), 2048)
    output.extend(b"\x00" * (final_size - len(output)))
    return bytes(output), replaced


def validate_repacked(
    original, repacked, pack_name, rebuilt_root, expected_records
):
    original_records = parse_resc(original)
    repacked_records = parse_resc(repacked)
    if [row[0] for row in original_records] != [row[0] for row in repacked_records]:
        raise ValueError(f"{pack_name}: record order/name changed")
    if len(repacked) % 2048:
        raise ValueError(f"{pack_name}: archive is not 2,048-byte aligned")

    checked_replacements = set()
    for index, ((name, old_offset, old_size), (_, new_offset, new_size)) in enumerate(
        zip(original_records, repacked_records)
    ):
        if new_offset % 16:
            raise ValueError(f"{pack_name}/{name}: record offset is not aligned")
        old_data = original[old_offset : old_offset + old_size]
        new_data = repacked[new_offset : new_offset + new_size]
        key = (pack_name, name)
        if key in expected_records:
            expected = (rebuilt_root / pack_name / f"{name}.bin").read_bytes()
            if new_data != expected:
                raise ValueError(f"{pack_name}/{name}: replacement mismatch")
            checked_replacements.add(key)
        elif new_data != old_data:
            raise ValueError(f"{pack_name}/{name}: untouched record changed")

        next_offset = (
            repacked_records[index + 1][1]
            if index + 1 < len(repacked_records)
            else len(repacked)
        )
        padding = repacked[new_offset + new_size : next_offset]
        if any(padding):
            raise ValueError(f"{pack_name}/{name}: nonzero alignment padding")

    expected_for_pack = {
        key for key in expected_records if key[0] == pack_name
    }
    if checked_replacements != expected_for_pack:
        raise ValueError(
            f"{pack_name}: replacement coverage mismatch "
            f"({len(checked_replacements)} != {len(expected_for_pack)})"
        )


def main():
    workspace = Path(__file__).resolve().parent
    project_root = workspace.parent
    original_root = project_root / "Original/PSP_GAME/USRDIR/Resource/scpack"
    output_root = project_root / "PSP_GAME/USRDIR/Resource/scpack"
    rebuilt_root = workspace / "tsqv_rebuilt/scpack"
    rebuilt_manifest_path = workspace / "tsqv_rebuilt/manifest.csv"
    repack_manifest_path = workspace / "tsqv_rebuilt/scpack_manifest.csv"

    expected_records = read_rebuilt_manifest(rebuilt_manifest_path)
    affected_packs = sorted({pack_name for pack_name, _ in expected_records})
    manifest_rows = []
    replaced_total = 0

    for pack_name in affected_packs:
        original_path = original_root / pack_name
        original = original_path.read_bytes()
        repacked, replaced = repack_archive(
            original, pack_name, rebuilt_root, expected_records
        )
        validate_repacked(
            original, repacked, pack_name, rebuilt_root, expected_records
        )

        output_path = output_root / pack_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary_path.write_bytes(repacked)
        temporary_path.replace(output_path)

        replaced_total += len(replaced)
        manifest_rows.append(
            {
                "File Path": f"scpack/{pack_name}",
                "Original Size": len(original),
                "Repacked Size": len(repacked),
                "Size Delta": len(repacked) - len(original),
                "Replaced TSQV Records": len(replaced),
                "SHA256": hashlib.sha256(repacked).hexdigest(),
            }
        )

    if replaced_total != len(expected_records):
        raise RuntimeError(
            f"replaced {replaced_total} TSQV records; expected {len(expected_records)}"
        )

    repack_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with repack_manifest_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Repacked scpack archives: {len(manifest_rows)}")
    print(f"Replaced TSQV records: {replaced_total}")
    print(f"Output root: {output_root}")
    print(f"Manifest: {repack_manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
