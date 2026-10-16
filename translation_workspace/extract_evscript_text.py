from __future__ import annotations

import csv
import struct
from collections import Counter, defaultdict
from pathlib import Path

from extract_tsqv import parse_resc


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Original" / "PSP_GAME" / "USRDIR" / "Resource" / "scpack"
OUTPUT = ROOT / "translation_workspace" / "evscript_text"


def iter_strings(record: bytes):
    # EVSCRIPT embeds display strings as a type-3 value followed by a
    # four-byte-aligned fixed-size Shift-JIS buffer.  Scanning these typed
    # values is safer than treating arbitrary Shift-JIS-looking byte runs as
    # text and preserves the exact field limit needed for reinsertion.
    for offset in range(0, len(record) - 12, 4):
        if struct.unpack_from("<I", record, offset)[0] != 3:
            continue
        field_size = struct.unpack_from("<I", record, offset + 4)[0]
        data_offset = offset + 8
        if not (4 <= field_size <= 256 and field_size % 4 == 0):
            continue
        if data_offset + field_size > len(record):
            continue
        field = record[data_offset : data_offset + field_size]
        terminator = field.find(b"\0")
        if terminator < 0 or any(field[terminator:]):
            continue
        raw = field[:terminator]
        try:
            text = raw.decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if text and any(ord(char) > 0x7F for char in text):
            yield offset, data_offset, field_size, raw, text


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    occurrences: list[dict[str, object]] = []
    locations: dict[str, list[str]] = defaultdict(list)
    limits: dict[str, list[int]] = defaultdict(list)

    for archive in sorted(SOURCE.glob("*.res")):
        container = archive.read_bytes()
        for record_name, record_offset, record_size in parse_resc(container):
            record = container[record_offset : record_offset + record_size]
            if record[:8] != b"EVSCRIPT":
                continue
            for header_offset, data_offset, field_size, raw, original in iter_strings(record):
                row = {
                    "Archive": archive.name,
                    "Record": record_name,
                    "Record Offset": f"0x{record_offset:X}",
                    "Record Size": record_size,
                    "String Header Offset": f"0x{header_offset:X}",
                    "String Data Offset": f"0x{data_offset:X}",
                    "Field Size": field_size,
                    "Original Bytes": len(raw),
                    "Original": original,
                }
                occurrences.append(row)
                locations[original].append(
                    f"{archive.name}/{record_name}+0x{data_offset:X}"
                )
                limits[original].append(field_size)

    counts = Counter(row["Original"] for row in occurrences)
    master = []
    for index, original in enumerate(sorted(counts)):
        master.append(
            {
                "Index": index,
                "Original": original,
                "Occurrence Count": counts[original],
                "Minimum Field Size": min(limits[original]),
                "Locations": " | ".join(locations[original]),
                "Translated": "",
            }
        )

    write_csv(
        OUTPUT / "evscript_occurrences.csv",
        [
            "Archive", "Record", "Record Offset", "Record Size",
            "String Header Offset", "String Data Offset", "Field Size",
            "Original Bytes", "Original",
        ],
        occurrences,
    )
    write_csv(
        OUTPUT / "evscript_translation.csv",
        [
            "Index", "Original", "Occurrence Count", "Minimum Field Size",
            "Locations", "Translated",
        ],
        master,
    )
    print(f"EVSCRIPT occurrences: {len(occurrences)}")
    print(f"Unique translation rows: {len(master)}")
    print(f"Archives: {len(set(row['Archive'] for row in occurrences))}")
    print(f"Records: {len(set((row['Archive'], row['Record']) for row in occurrences))}")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
