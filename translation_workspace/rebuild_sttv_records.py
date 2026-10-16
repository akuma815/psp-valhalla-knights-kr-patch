import csv
import hashlib
import struct
import sys
from collections import defaultdict
from pathlib import Path

from extract_tsqv import parse_resc
from rebuild_tsqv_records import (
    build_character_mapping,
    hybrid_encode_strict,
    read_csv,
)


MANIFEST_FIELDS = [
    "File Path",
    "Record Name",
    "String Count",
    "Original Size",
    "Rebuilt Content Size",
    "Padded Size",
    "Remaining Bytes",
    "Expanded Original Slots",
    "Max Slot Overflow",
    "Original SHA256",
    "Rebuilt SHA256",
]


def align_up(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def parse_sttv(record_data, label):
    if len(record_data) < 16 or record_data[:8] != b"STTV1.00":
        raise ValueError(f"{label}: not a complete STTV1.00 record")

    string_count, table_offset = struct.unpack_from("<II", record_data, 8)
    if table_offset != 0x10:
        raise ValueError(f"{label}: unexpected table offset {table_offset:#x}")

    data_offset = table_offset + string_count * 8
    if data_offset > len(record_data):
        raise ValueError(f"{label}: index table exceeds record size")

    entries = []
    expected_offset = data_offset
    for string_index in range(string_count):
        entry_offset = table_offset + string_index * 8
        string_offset, string_length = struct.unpack_from(
            "<II", record_data, entry_offset
        )
        if string_offset != expected_offset:
            raise ValueError(
                f"{label}: slot {string_index} is not contiguous/aligned: "
                f"{string_offset:#x} != {expected_offset:#x}"
            )
        if string_offset % 4:
            raise ValueError(f"{label}: slot {string_index} is not 4-byte aligned")

        terminator_offset = string_offset + string_length
        if terminator_offset >= len(record_data):
            raise ValueError(f"{label}: slot {string_index} exceeds record size")
        if record_data[terminator_offset] != 0:
            raise ValueError(f"{label}: slot {string_index} has no null terminator")

        next_offset = align_up(terminator_offset + 1, 4)
        if next_offset > len(record_data):
            raise ValueError(f"{label}: slot {string_index} padding exceeds record")
        if any(record_data[terminator_offset + 1 : next_offset]):
            raise ValueError(f"{label}: slot {string_index} has nonzero padding")

        entries.append((entry_offset, string_offset, string_length, next_offset))
        expected_offset = next_offset

    if expected_offset != len(record_data):
        raise ValueError(
            f"{label}: string area ends at {expected_offset:#x}, "
            f"record ends at {len(record_data):#x}"
        )
    return string_count, table_offset, data_offset, entries


def rebuild_sttv(record_data, rows, char_to_sjis, label):
    string_count, _, data_offset, entries = parse_sttv(record_data, label)
    if len(rows) != string_count:
        raise ValueError(
            f"{label}: CSV rows {len(rows)} do not match strings {string_count}"
        )

    rows_by_index = {}
    for row in rows:
        string_index = int(row["Index"])
        if string_index in rows_by_index:
            raise ValueError(f"{label}: duplicate CSV index {string_index}")
        rows_by_index[string_index] = row
    if set(rows_by_index) != set(range(string_count)):
        missing = set(range(string_count)) - set(rows_by_index)
        extra = set(rows_by_index) - set(range(string_count))
        raise ValueError(
            f"{label}: CSV index coverage mismatch: "
            f"missing={len(missing)}, extra={len(extra)}"
        )

    rebuilt = bytearray(record_data[:data_offset])
    expanded_slots = 0
    max_slot_overflow = 0

    for string_index, (entry_offset, string_offset, original_length, _) in enumerate(
        entries
    ):
        row = rows_by_index[string_index]
        original_bytes = record_data[
            string_offset : string_offset + original_length
        ]
        try:
            original_text = original_bytes.decode("shift_jis", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"{label}: original slot {string_index} is not Shift-JIS"
            ) from exc
        csv_original = row["Original"].replace("\r\n", "\n")
        if original_text != csv_original:
            raise ValueError(
                f"{label}: source mismatch at index {string_index}: "
                f"{original_text!r} != {csv_original!r}"
            )

        selected_text = (row["Translated"] or row["Original"]).replace(
            "\r\n", "\n"
        )
        encoded = hybrid_encode_strict(selected_text, char_to_sjis)
        overflow = max(0, len(encoded) - original_length)
        if overflow:
            expanded_slots += 1
            max_slot_overflow = max(max_slot_overflow, overflow)

        rebuilt_offset = len(rebuilt)
        struct.pack_into(
            "<II", rebuilt, entry_offset, rebuilt_offset, len(encoded)
        )
        rebuilt.extend(encoded)
        rebuilt.append(0)
        rebuilt.extend(b"\x00" * (align_up(len(rebuilt), 4) - len(rebuilt)))

    content_size = len(rebuilt)
    if content_size > len(record_data):
        raise ValueError(
            f"{label}: rebuilt content exceeds original record by "
            f"{content_size - len(record_data)} bytes"
        )
    rebuilt.extend(b"\x00" * (len(record_data) - content_size))
    if len(rebuilt) != len(record_data):
        raise RuntimeError(f"{label}: padded record size changed")

    return bytes(rebuilt), {
        "content_size": content_size,
        "remaining_bytes": len(record_data) - content_size,
        "expanded_slots": expanded_slots,
        "max_slot_overflow": max_slot_overflow,
    }


def rebuild_sttv_preserving_slots(record_data, rows, char_to_sjis, label):
    string_count, _, _, entries = parse_sttv(record_data, label)
    if len(rows) != string_count:
        raise ValueError(
            f"{label}: CSV rows {len(rows)} do not match strings {string_count}"
        )
    rows_by_index = {int(row["Index"]): row for row in rows}
    if len(rows_by_index) != len(rows) or set(rows_by_index) != set(
        range(string_count)
    ):
        raise ValueError(f"{label}: CSV index coverage mismatch")

    rebuilt = bytearray(record_data)
    remaining_bytes = 0
    for string_index, (
        entry_offset,
        string_offset,
        original_length,
        next_offset,
    ) in enumerate(entries):
        row = rows_by_index[string_index]
        original_text = record_data[
            string_offset : string_offset + original_length
        ].decode("shift_jis", errors="strict")
        csv_original = row["Original"].replace("\r\n", "\n")
        if original_text != csv_original:
            raise ValueError(f"{label}: source mismatch at index {string_index}")

        selected_text = (row["Translated"] or row["Original"]).replace(
            "\r\n", "\n"
        )
        encoded = hybrid_encode_strict(selected_text, char_to_sjis)
        capacity = next_offset - string_offset - 1
        if len(encoded) > capacity:
            raise ValueError(
                f"{label}: fixed slot {string_index} exceeds capacity by "
                f"{len(encoded) - capacity} bytes"
            )
        struct.pack_into(
            "<II", rebuilt, entry_offset, string_offset, len(encoded)
        )
        rebuilt[string_offset:next_offset] = (encoded + b"\0").ljust(
            next_offset - string_offset, b"\0"
        )
        remaining_bytes += capacity - len(encoded)

    return bytes(rebuilt), {
        "content_size": len(rebuilt),
        "remaining_bytes": remaining_bytes,
        "expanded_slots": 0,
        "max_slot_overflow": 0,
    }


def main():
    workspace = Path(__file__).resolve().parent
    project_root = workspace.parent
    output_root = workspace / "sttv_rebuild/records"
    manifest_path = workspace / "sttv_rebuild/manifest.csv"

    table_rows = read_csv(workspace / "total_translation.csv")
    tsqv_rows = read_csv(workspace / "tsqv_translation.csv")
    char_to_sjis = build_character_mapping(project_root, table_rows, tsqv_rows)

    rows_by_record = defaultdict(list)
    file_paths = {}
    for row in table_rows:
        record_name = row["File Path"].replace("\\", "/").split("/")[-1].lower()
        rows_by_record[record_name].append(row)
        file_paths.setdefault(record_name, row["File Path"])
        if file_paths[record_name] != row["File Path"]:
            raise ValueError(f"{record_name}: inconsistent CSV file path")

    original_tbldata_path = (
        project_root / "Original/PSP_GAME/USRDIR/Resource/tbldata/tbldata.res"
    )
    original_tbldata = original_tbldata_path.read_bytes()
    original_records = {
        name.lower(): original_tbldata[offset : offset + size]
        for name, offset, size in parse_resc(original_tbldata)
    }

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    total_strings = 0
    total_expanded_slots = 0
    for record_name in sorted(rows_by_record):
        if record_name not in original_records:
            raise KeyError(f"missing tbldata record: {record_name}")
        original_record = original_records[record_name]
        label = f"tbldata/{record_name}"
        rows = sorted(rows_by_record[record_name], key=lambda row: int(row["Index"]))
        if record_name == "etstrtbl":
            rebuilt_record, stats = rebuild_sttv_preserving_slots(
                original_record, rows, char_to_sjis, label
            )
        else:
            rebuilt_record, stats = rebuild_sttv(
                original_record, rows, char_to_sjis, label
            )

        output_path = output_root / f"{record_name}.bin"
        output_path.write_bytes(rebuilt_record)
        total_strings += len(rows)
        total_expanded_slots += stats["expanded_slots"]
        manifest_rows.append(
            {
                "File Path": file_paths[record_name],
                "Record Name": record_name,
                "String Count": len(rows),
                "Original Size": len(original_record),
                "Rebuilt Content Size": stats["content_size"],
                "Padded Size": len(rebuilt_record),
                "Remaining Bytes": stats["remaining_bytes"],
                "Expanded Original Slots": stats["expanded_slots"],
                "Max Slot Overflow": stats["max_slot_overflow"],
                "Original SHA256": hashlib.sha256(original_record).hexdigest(),
                "Rebuilt SHA256": hashlib.sha256(rebuilt_record).hexdigest(),
            }
        )

    if len(manifest_rows) != 17:
        raise RuntimeError(f"rebuilt {len(manifest_rows)} STTV records; expected 17")
    if total_strings != len(table_rows):
        raise RuntimeError(
            f"rebuilt {total_strings} strings; expected {len(table_rows)}"
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Custom font codes loaded: {len(char_to_sjis)}")
    print(f"Rebuilt STTV records: {len(manifest_rows)}")
    print(f"Rebuilt strings: {total_strings}")
    print(f"Expanded original slots: {total_expanded_slots}")
    print("Truncated strings: 0")
    print("Record size overflows: 0")
    print(f"Output root: {output_root}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
