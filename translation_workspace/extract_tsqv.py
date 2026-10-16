import argparse
import csv
import os
import struct
from pathlib import Path


CSV_FIELDS = ["File Path", "Index", "Offset", "Original", "Translated"]


def parse_resc(data):
    if data[:4] != b"RESC":
        raise ValueError("not a RESC archive")
    count = struct.unpack_from("<I", data, 4)[0]
    records = []
    for index in range(count):
        record_offset = 8 + index * 16
        name_bytes = bytearray(data[record_offset : record_offset + 8])
        name_bytes.reverse()
        name = bytes(name_bytes).strip(b"\x00").decode("ascii", errors="strict")
        size, offset = struct.unpack_from("<II", data, record_offset + 8)
        if offset + size > len(data):
            raise ValueError(f"RESC record {name!r} exceeds archive size")
        records.append((name, offset, size))
    return records


def is_scenario_text(text):
    if not text or not text.strip(" \u3000"):
        return False
    if any(ord(char) < 0x20 for char in text):
        return False

    # TSQV control values can decode as short ASCII strings such as " N" or
    # "0u".  Actual Japanese scenario strings contain at least one character
    # in these Japanese/CJK/full-width ranges.
    return any(
        0x3000 <= ord(char) <= 0x30FF
        or 0x3400 <= ord(char) <= 0x9FFF
        or 0xFF01 <= ord(char) <= 0xFFEF
        for char in text
    )


def extract_tsqv_record(record_data):
    if record_data[:8] != b"TSQV1.10":
        return []
    if len(record_data) < 16:
        raise ValueError("truncated TSQV header")

    instruction_count, instruction_offset, index_offset, data_offset = (
        struct.unpack_from("<HHHH", record_data, 8)
    )
    expected_index_offset = instruction_offset + instruction_count * 6
    if instruction_offset != 0x10 or index_offset != expected_index_offset:
        raise ValueError(
            f"unexpected TSQV instruction/index boundary: "
            f"{instruction_offset:#x}, {index_offset:#x}"
        )
    if not (index_offset <= data_offset <= len(record_data)):
        raise ValueError("invalid TSQV string table boundaries")
    if (data_offset - index_offset) % 4:
        raise ValueError("TSQV string index table is not 4-byte aligned")

    rows = []
    slot_count = (data_offset - index_offset) // 4
    for slot_index in range(slot_count):
        entry_offset = index_offset + slot_index * 4
        string_offset, slot_size = struct.unpack_from("<HH", record_data, entry_offset)
        string_end = string_offset + slot_size
        if string_offset < data_offset or string_end > len(record_data):
            raise ValueError(
                f"TSQV slot {slot_index} exceeds record: "
                f"{string_offset:#x}+{slot_size:#x}"
            )

        raw = record_data[string_offset:string_end]
        payload = raw.rstrip(b"\x00")
        if not payload:
            continue
        try:
            text = payload.decode("shift_jis", errors="strict")
        except UnicodeDecodeError:
            continue
        if not is_scenario_text(text):
            continue

        rows.append(
            {
                "Index": slot_index,
                "Offset": string_offset,
                "Original": text,
                "Translated": "",
            }
        )
    return rows


def load_existing_translations(paths):
    translations = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                key = (
                    row.get("File Path", ""),
                    row.get("Index", ""),
                    row.get("Offset", ""),
                    row.get("Original", ""),
                )
                if row.get("Translated", ""):
                    translations[key] = row["Translated"]
    return translations


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def safe_csv_name(pack_name, record_name):
    return f"{Path(pack_name).stem}_{record_name}.csv"


def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    parser = argparse.ArgumentParser(
        description="Extract RESC-embedded TSQV1.10 scenario strings to CSV."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=project_root / "Original" / "PSP_GAME" / "USRDIR" / "Resource" / "scpack",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "tsqv_csv",
    )
    parser.add_argument(
        "--total-output",
        type=Path,
        default=script_dir / "tsqv_translation.csv",
    )
    args = parser.parse_args()

    existing_paths = [args.total_output]
    if args.output_dir.exists():
        existing_paths.extend(args.output_dir.glob("*.csv"))
    translations = load_existing_translations(existing_paths)

    total_rows = []
    record_csv_count = 0
    tsqv_record_count = 0
    for pack_path in sorted(args.source.glob("*.res")):
        archive = pack_path.read_bytes()
        for record_name, record_offset, record_size in parse_resc(archive):
            record_data = archive[record_offset : record_offset + record_size]
            if not record_data.startswith(b"TSQV1.10"):
                continue
            tsqv_record_count += 1
            extracted = extract_tsqv_record(record_data)
            if not extracted:
                continue

            file_path = f"scpack/{pack_path.name}/{record_name}"
            record_rows = []
            for row in extracted:
                output_row = {
                    "File Path": file_path,
                    "Index": row["Index"],
                    "Offset": row["Offset"],
                    "Original": row["Original"],
                    "Translated": "",
                }
                key = tuple(str(output_row[field]) for field in CSV_FIELDS[:4])
                output_row["Translated"] = translations.get(key, "")
                record_rows.append(output_row)

            write_csv(
                args.output_dir / safe_csv_name(pack_path.name, record_name),
                record_rows,
            )
            record_csv_count += 1
            total_rows.extend(record_rows)

    write_csv(args.total_output, total_rows)
    print(f"Scanned TSQV records: {tsqv_record_count}")
    print(f"Created record CSV files: {record_csv_count}")
    print(f"Extracted scenario text rows: {len(total_rows)}")
    print(f"Unified CSV: {args.total_output}")


if __name__ == "__main__":
    main()
