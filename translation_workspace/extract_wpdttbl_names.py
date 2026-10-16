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
OUTPUT = WORKSPACE / "wpdttbl_translation.csv"

SIGNATURE = b"WDTV1.15"
RECORD_SIZE = 52
NAME_OFFSET = 0
NAME_SIZE = 24


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
        raise ValueError(f"unexpected wpdttbl signature: {data[:8]!r}")
    count, table_offset = struct.unpack_from("<II", data, 8)
    table_end = table_offset + count * RECORD_SIZE
    if table_end != len(data):
        raise ValueError(
            f"unexpected wpdttbl layout: table end {table_end} != {len(data)}"
        )

    rows: list[dict[str, str | int]] = []
    for index in range(count):
        record_offset = table_offset + index * RECORD_SIZE
        name_start = record_offset + NAME_OFFSET
        name_field = data[name_start : name_start + NAME_SIZE]
        name_raw = name_field.split(b"\0", 1)[0]
        try:
            original = name_raw.decode("shift_jis")
        except UnicodeDecodeError as exc:
            raise ValueError(f"index {index}: invalid Shift-JIS weapon name") from exc

        rows.append(
            {
                "File Path": "tbldata/wpdttbl",
                "Index": index,
                "Record Offset": f"0x{record_offset:X}",
                "Name Offset": f"0x{name_start:X}",
                "Field Size": NAME_SIZE,
                "Max Encoded Bytes": NAME_SIZE,
                "Original Bytes": len(name_raw),
                "Original": original,
                "Translated": "",
            }
        )
    return table_offset, rows


def main() -> None:
    original_container = ORIGINAL_TBLDATA.read_bytes()
    original_record, original_data = read_record(original_container, "wpdttbl")
    table_offset, rows = parse_names(original_data)

    if PATCHED_TBLDATA.exists():
        patched_container = PATCHED_TBLDATA.read_bytes()
        _, patched_data = read_record(patched_container, "wpdttbl")
        _, patched_rows = parse_names(patched_data)
        if [row["Original"] for row in patched_rows] != [
            row["Original"] for row in rows
        ]:
            raise ValueError("patched wpdttbl name array differs from original")

    fieldnames = [
        "File Path",
        "Index",
        "Record Offset",
        "Name Offset",
        "Field Size",
        "Max Encoded Bytes",
        "Original Bytes",
        "Original",
        "Translated",
    ]
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    duplicate_rows = len(rows) - len({row["Original"] for row in rows})
    print(f"Source record offset: 0x{original_record['offset']:X}")
    print(f"wpdttbl table offset: 0x{table_offset:X}")
    print(f"Extracted weapon names: {len(rows)}")
    print(f"Empty names: {sum(not row['Original'] for row in rows)}")
    print(f"Duplicate rows: {duplicate_rows}")
    print(f"Maximum field payload: {NAME_SIZE} bytes")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
