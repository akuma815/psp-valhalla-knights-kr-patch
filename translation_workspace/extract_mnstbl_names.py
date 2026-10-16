from __future__ import annotations

import csv
import struct
from pathlib import Path

from in_place_patcher import parse_res_header


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
ORIGINAL_TBLDATA = (
    ROOT / "Original" / "PSP_GAME" / "USRDIR" / "Resource" / "tbldata" / "tbldata.res"
)
PATCHED_TBLDATA = (
    ROOT / "PSP_GAME" / "USRDIR" / "Resource" / "tbldata" / "tbldata.res"
)
OUTPUT = WORKSPACE / "mnstbl_translation.csv"

SIGNATURE = b"MNTV1.21"
RECORD_SIZE = 60
NAME_OFFSET = 24
NAME_SIZE = 32


def read_record(container: bytes, name: str) -> tuple[dict, bytes]:
    record = next(
        (item for item in parse_res_header(container) if item["name"].lower() == name),
        None,
    )
    if record is None:
        raise KeyError(f"record not found: {name}")
    start = record["offset"]
    return record, container[start : start + record["size"]]


def parse_names(data: bytes) -> tuple[int, list[dict[str, str | int]]]:
    if data[:8] != SIGNATURE:
        raise ValueError(f"unexpected mnstbl signature: {data[:8]!r}")

    count, table_offset = struct.unpack_from("<II", data, 8)
    table_end = table_offset + count * RECORD_SIZE
    if table_end > len(data):
        raise ValueError(
            f"mnstbl name table exceeds record: {table_end} > {len(data)}"
        )

    rows: list[dict[str, str | int]] = []
    for index in range(count):
        record_offset = table_offset + index * RECORD_SIZE
        record_id_raw = data[record_offset : record_offset + 8].split(b"\0", 1)[0]
        name_start = record_offset + NAME_OFFSET
        name_raw = data[name_start : name_start + NAME_SIZE].split(b"\0", 1)[0]

        try:
            record_id = record_id_raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError(f"index {index}: invalid ASCII record ID") from exc
        try:
            original = name_raw.decode("shift_jis")
        except UnicodeDecodeError as exc:
            raise ValueError(f"index {index}: invalid Shift-JIS monster name") from exc

        rows.append(
            {
                "File Path": "tbldata/mnstbl",
                "Index": index,
                "Record ID": record_id,
                "Record Offset": f"0x{record_offset:X}",
                "Name Offset": f"0x{name_start:X}",
                "Field Size": NAME_SIZE,
                "Original Bytes": len(name_raw),
                "Original": original,
                "Translated": "",
            }
        )

    return table_offset, rows


def main() -> None:
    original_container = ORIGINAL_TBLDATA.read_bytes()
    original_record, original_data = read_record(original_container, "mnstbl")
    table_offset, rows = parse_names(original_data)

    if PATCHED_TBLDATA.exists():
        patched_container = PATCHED_TBLDATA.read_bytes()
        _, patched_data = read_record(patched_container, "mnstbl")
        _, patched_rows = parse_names(patched_data)
        original_pairs = [
            (row["Record ID"], row["Original"]) for row in rows
        ]
        patched_pairs = [
            (row["Record ID"], row["Original"]) for row in patched_rows
        ]
        if patched_pairs != original_pairs:
            raise ValueError("patched mnstbl name array differs from original")

    fieldnames = [
        "File Path",
        "Index",
        "Record ID",
        "Record Offset",
        "Name Offset",
        "Field Size",
        "Original Bytes",
        "Original",
        "Translated",
    ]
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    empty_names = sum(not row["Original"] for row in rows)
    duplicate_names = len(rows) - len({row["Original"] for row in rows})
    print(f"Source record offset: 0x{original_record['offset']:X}")
    print(f"mnstbl table offset: 0x{table_offset:X}")
    print(f"Extracted monster names: {len(rows)}")
    print(f"Empty names: {empty_names}")
    print(f"Duplicate rows: {duplicate_names}")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
