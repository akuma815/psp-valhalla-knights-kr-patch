from __future__ import annotations

import csv
import struct
from collections import defaultdict
from pathlib import Path

from extract_tsqv import parse_resc
from rebuild_tsqv_records import build_character_mapping, hybrid_encode_strict, read_csv


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
SOURCE = ROOT / "Original" / "PSP_GAME" / "USRDIR" / "Resource" / "scpack"
TARGET = ROOT / "PSP_GAME" / "USRDIR" / "Resource" / "scpack"
CSV_ROOT = WORKSPACE / "evscript_text"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def record_map(container: bytes) -> dict[str, tuple[int, int]]:
    return {name: (offset, size) for name, offset, size in parse_resc(container)}


def main() -> None:
    translations = csv_rows(CSV_ROOT / "evscript_translation.csv")
    translated = sum(bool(row["Translated"].strip()) for row in translations)
    if translated != len(translations):
        print(f"Skipped EVSCRIPT: translations {translated}/{len(translations)}")
        return
    translated_by_original = {
        row["Original"]: row["Translated"].strip() for row in translations
    }
    occurrences = csv_rows(CSV_ROOT / "evscript_occurrences.csv")

    table_rows = read_csv(WORKSPACE / "total_translation.csv")
    tsqv_rows = read_csv(WORKSPACE / "tsqv_translation.csv")
    char_to_sjis = build_character_mapping(ROOT, table_rows, tsqv_rows)

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in occurrences:
        grouped[row["Archive"]].append(row)

    report = []
    for archive_name, rows in sorted(grouped.items()):
        original_container = (SOURCE / archive_name).read_bytes()
        target_path = TARGET / archive_name
        target_container = bytearray(target_path.read_bytes())
        original_records = record_map(original_container)
        target_records = record_map(target_container)

        for row in rows:
            record_name = row["Record"]
            original_offset, original_size = original_records[record_name]
            target_offset, target_size = target_records[record_name]
            if original_size != target_size:
                raise ValueError(f"{archive_name}/{record_name}: record size changed")
            data_offset = int(row["String Data Offset"], 16)
            field_size = int(row["Field Size"])
            original_field = original_container[
                original_offset + data_offset : original_offset + data_offset + field_size
            ]
            original_text = original_field.split(b"\0", 1)[0].decode("shift_jis")
            if original_text != row["Original"]:
                raise ValueError(
                    f"{archive_name}/{record_name}+0x{data_offset:X}: source mismatch"
                )
            translated_text = translated_by_original[original_text]
            encoded = hybrid_encode_strict(translated_text, char_to_sjis)
            limit = field_size - 1
            if len(encoded) > limit:
                raise ValueError(
                    f"{archive_name}/{record_name} {translated_text!r}: "
                    f"{len(encoded)} bytes exceeds {limit}"
                )
            start = target_offset + data_offset
            target_container[start : start + field_size] = encoded.ljust(field_size, b"\0")
            report.append(
                {
                    "Archive": archive_name,
                    "Record": record_name,
                    "String Data Offset": f"0x{data_offset:X}",
                    "Original": original_text,
                    "Translated": translated_text,
                    "Encoded Bytes": len(encoded),
                    "Limit": limit,
                    "Remaining": limit - len(encoded),
                    "Fit": "PASS",
                }
            )
        target_path.write_bytes(target_container)

    report_path = CSV_ROOT / "validation_report.csv"
    fields = [
        "Archive", "Record", "String Data Offset", "Original", "Translated",
        "Encoded Bytes", "Limit", "Remaining", "Fit",
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report)
    print(f"Rebuilt EVSCRIPT strings: {len(report)}")
    print(f"Validation: {report_path}")


if __name__ == "__main__":
    main()
