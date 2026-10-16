from __future__ import annotations

import csv
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from in_place_patcher import parse_res_header
from rebuild_tsqv_records import (
    build_character_mapping,
    hybrid_encode_strict,
    read_csv,
)


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
ORIGINAL_TBLDATA = (
    ROOT / "Original" / "PSP_GAME" / "USRDIR" / "Resource" / "tbldata" / "tbldata.res"
)
PATCHED_TBLDATA = (
    ROOT / "PSP_GAME" / "USRDIR" / "Resource" / "tbldata" / "tbldata.res"
)
OUTPUT = WORKSPACE / "fixed_data_rebuild"


@dataclass(frozen=True)
class FixedTableSpec:
    name: str
    csv_name: str
    signature: bytes
    record_size: int
    name_offset: int
    name_size: int
    mode: str = "fixed"
    sparse: bool = False


SPECS = (
    FixedTableSpec("wpdttbl", "wpdttbl_translation.csv", b"WDTV1.15", 52, 0, 24),
    FixedTableSpec("mnstbl", "mnstbl_translation.csv", b"MNTV1.21", 60, 24, 32),
    FixedTableSpec("pmprmtbl", "pmprmtbl_translation.csv", b"PMTV1.01", 72, 0, 16),
    FixedTableSpec("mgdttbl", "mgdttbl_translation.csv", b"MDTV1.25", 24, 0, 16),
    FixedTableSpec("uidttbl", "uidttbl_translation.csv", b"UDTV1.06", 28, 0, 20),
    FixedTableSpec("uitmtbl", "uitmtbl_translation.csv", b"UITV1.11", 32, 0, 20),
    FixedTableSpec("sidttbl", "sidttbl_translation.csv", b"SDTV1.00", 24, 0, 24),
    FixedTableSpec("amdttbl", "amdttbl_translation.csv", b"ADTV1.12", 48, 0, 24, sparse=True),
    FixedTableSpec("magictbl", "magictbl_translation.csv", b"MCTV1.00", 28, 0, 16),
    FixedTableSpec("mmgtbl", "mmgtbl_translation.csv", b"MGTV1.00", 64, 0, 64, sparse=True),
    FixedTableSpec("sitmtbl", "sitmtbl_translation.csv", b"SITV1.11", 24, 0, 16),
    FixedTableSpec("magictbl", "magictbl_description_translation.csv", b"MCTV1.00", 28, 20, 24, mode="pointer"),
    FixedTableSpec("sitmtbl", "sitmtbl_description_translation.csv", b"SITV1.11", 24, 16, 20, mode="pointer"),
    FixedTableSpec("uitmtbl", "uitmtbl_description_translation.csv", b"UITV1.11", 32, 24, 28, mode="pointer"),
)


def find_record(container: bytes, target: str) -> dict:
    record = next(
        (item for item in parse_res_header(container) if item["name"].lower() == target),
        None,
    )
    if record is None:
        raise KeyError(target)
    return record


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"Index", "Original", "Translated"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"{path}: missing required columns {sorted(required)}")
    return rows


def is_complete(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(row["Translated"].strip() for row in rows)


def rebuild_record(
    original: bytes,
    base: bytes,
    rows: list[dict[str, str]],
    spec: FixedTableSpec,
    char_to_sjis: dict[str, bytes],
) -> tuple[bytes, list[dict[str, str | int]]]:
    if original[:8] != spec.signature:
        raise ValueError(f"{spec.name}: unexpected signature {original[:8]!r}")
    count, table_offset = struct.unpack_from("<II", original, 8)
    if table_offset + count * spec.record_size > len(original):
        raise ValueError(f"{spec.name}: fixed table exceeds record")
    if not spec.sparse and len(rows) != count:
        raise ValueError(f"{spec.name}: CSV rows {len(rows)} != record count {count}")

    rows_by_index = {int(row["Index"]): row for row in rows}
    expected = set(rows_by_index) if spec.sparse else set(range(count))
    if len(rows_by_index) != len(rows) or set(rows_by_index) != expected:
        raise ValueError(f"{spec.name}: CSV index coverage mismatch")
    if any(index < 0 or index >= count for index in rows_by_index):
        raise ValueError(f"{spec.name}: CSV index outside record count")

    rebuilt = bytearray(base)
    report: list[dict[str, str | int]] = []
    # These are fixed-width fields.  Shorter names are zero padded, while a
    # name may legally occupy the full field without a null terminator.
    for index in sorted(rows_by_index):
        row = rows_by_index[index]
        record_offset = table_offset + index * spec.record_size
        if spec.mode == "fixed":
            name_start = record_offset + spec.name_offset
            payload_limit = spec.name_size
        elif spec.mode == "pointer":
            relative_offset = struct.unpack_from("<I", original, record_offset + spec.name_offset)[0]
            payload_limit = struct.unpack_from("<I", original, record_offset + spec.name_size)[0]
            name_start = relative_offset
            if name_start + payload_limit > len(original):
                raise ValueError(f"{spec.name}[{index}]: pointed field exceeds record")
        else:
            raise ValueError(f"{spec.name}: unsupported mode {spec.mode}")
        field = original[name_start : name_start + payload_limit]
        raw_original = field.split(b"\0", 1)[0]
        try:
            original_text = raw_original.decode("shift_jis")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{spec.name}[{index}]: invalid original Shift-JIS") from exc
        if original_text != row["Original"]:
            raise ValueError(
                f"{spec.name}[{index}]: source mismatch "
                f"{original_text!r} != {row['Original']!r}"
            )

        translated = row["Translated"].strip()
        encoded = hybrid_encode_strict(translated, char_to_sjis)
        if len(encoded) > payload_limit:
            raise ValueError(
                f"{spec.name}[{index}] {translated!r}: "
                f"{len(encoded)} bytes exceeds {payload_limit}"
            )
        rebuilt[name_start : name_start + payload_limit] = encoded.ljust(
            payload_limit, b"\0"
        )
        report.append(
            {
                "Record": spec.name,
                "Index": index,
                "Original": original_text,
                "Translated": translated,
                "Encoded Bytes": len(encoded),
                "Limit": payload_limit,
                "Remaining": payload_limit - len(encoded),
                "Fit": "PASS",
            }
        )
    return bytes(rebuilt), report


def main() -> None:
    original_container = ORIGINAL_TBLDATA.read_bytes()
    patched_container = bytearray(PATCHED_TBLDATA.read_bytes())

    completed: list[tuple[FixedTableSpec, list[dict[str, str]]]] = []
    for spec in SPECS:
        csv_path = WORKSPACE / spec.csv_name
        if not csv_path.exists():
            print(f"Skipped {spec.name}: CSV not found")
            continue
        rows = read_rows(csv_path)
        translated_count = sum(bool(row["Translated"].strip()) for row in rows)
        if not is_complete(rows):
            print(f"Skipped {spec.name}: translations {translated_count}/{len(rows)}")
            continue
        completed.append((spec, rows))

    if not completed:
        print("No completed fixed-name table; patched tbldata left unchanged.")
        return

    table_rows = read_csv(WORKSPACE / "total_translation.csv")
    tsqv_rows = read_csv(WORKSPACE / "tsqv_translation.csv")
    # build_character_mapping() already loads every completed fixed-name CSV
    # after the STTV and TSQV rows.  Passing fixed rows here a second time
    # changed the character ordering and made the bytes written below disagree
    # with the mapping installed in fonttbl/GIM.  That manifested as blank or
    # incorrect fixed names even though their CSV translations were complete.
    char_to_sjis = build_character_mapping(ROOT, table_rows, tsqv_rows)

    OUTPUT.mkdir(exist_ok=True)
    all_report: list[dict[str, str | int]] = []
    for spec, rows in completed:
        original_record = find_record(original_container, spec.name)
        current_record = find_record(patched_container, spec.name)
        if original_record["size"] != current_record["size"]:
            raise ValueError(f"{spec.name}: original/current record size mismatch")
        start = original_record["offset"]
        original = original_container[start : start + original_record["size"]]
        current_start = current_record["offset"]
        base = bytes(patched_container[current_start : current_start + current_record["size"]])
        rebuilt, report = rebuild_record(original, base, rows, spec, char_to_sjis)

        patched_container[current_start : current_start + current_record["size"]] = rebuilt
        (OUTPUT / f"{spec.name}.bin").write_bytes(rebuilt)
        all_report.extend(report)
        print(
            f"Rebuilt {spec.name}: {len(rows)} fields, "
            f"SHA256 {hashlib.sha256(rebuilt).hexdigest()}"
        )

    PATCHED_TBLDATA.write_bytes(patched_container)
    report_path = OUTPUT / "validation_report.csv"
    fields = [
        "Record", "Index", "Original", "Translated", "Encoded Bytes",
        "Limit", "Remaining", "Fit",
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_report)
    print(f"Patched: {PATCHED_TBLDATA}")
    print(f"Validation: {report_path}")


if __name__ == "__main__":
    main()
