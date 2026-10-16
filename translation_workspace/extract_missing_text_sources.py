from __future__ import annotations

import csv
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from extract_tsqv import extract_tsqv_record, parse_resc
from in_place_patcher import parse_res_header


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
ORIGINAL_TBLDATA = (
    ROOT / "Original/PSP_GAME/USRDIR/Resource/tbldata/tbldata.res"
)
ORIGINAL_SCPACK = ROOT / "Original/PSP_GAME/USRDIR/Resource/scpack"

FIELDS = [
    "File Path",
    "Category",
    "Index",
    "Record Offset",
    "Offset",
    "Field Size",
    "Original Bytes",
    "Original",
    "Translated",
]


@dataclass(frozen=True)
class FixedTextSpec:
    table: str
    signature: bytes
    record_size: int
    text_offset: int
    text_size: int
    category: str


FIXED_SPECS = (
    FixedTextSpec("amdttbl", b"ADTV1.12", 48, 0, 24, "방어구명"),
    FixedTextSpec("magictbl", b"MCTV1.00", 28, 0, 16, "마법 계통명"),
    FixedTextSpec("mmgtbl", b"MGTV1.00", 64, 0, 64, "메뉴/선택 안내문"),
    FixedTextSpec("sitmtbl", b"SITV1.11", 24, 0, 16, "시나리오 아이템명"),
)


@dataclass(frozen=True)
class PointerTextSpec:
    table: str
    signature: bytes
    record_size: int
    pointer_offset: int
    size_offset: int
    category: str


POINTER_SPECS = (
    PointerTextSpec(
        "magictbl", b"MCTV1.00", 28, 20, 24, "마법 효과 설명"
    ),
    PointerTextSpec(
        "sitmtbl", b"SITV1.11", 24, 16, 20, "시나리오 아이템 설명"
    ),
    PointerTextSpec(
        "uitmtbl", b"UITV1.11", 32, 24, 28, "일반 아이템 설명"
    ),
)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_rows(path: Path, rows: list[dict[str, str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def translation_lookup() -> dict[str, str]:
    candidates: defaultdict[str, set[str]] = defaultdict(set)
    paths = [WORKSPACE / "total_translation.csv", WORKSPACE / "tsqv_translation.csv"]
    paths.extend(sorted(WORKSPACE.glob("*tbl_translation.csv")))
    for path in paths:
        for row in read_rows(path):
            original = row.get("Original", "")
            translated = row.get("Translated", "").strip()
            if original and translated:
                candidates[original].add(translated)
    return {
        original: next(iter(values))
        for original, values in candidates.items()
        if len(values) == 1
    }


def preserved_output_translations() -> dict[tuple[str, str, str], str]:
    preserved: dict[tuple[str, str, str], str] = {}
    for path in (
        WORKSPACE / "amdttbl_translation.csv",
        WORKSPACE / "magictbl_translation.csv",
        WORKSPACE / "mmgtbl_translation.csv",
        WORKSPACE / "sitmtbl_translation.csv",
        WORKSPACE / "magictbl_description_translation.csv",
        WORKSPACE / "sitmtbl_description_translation.csv",
        WORKSPACE / "uitmtbl_description_translation.csv",
    ):
        for row in read_rows(path):
            translated = row.get("Translated", "").strip()
            if translated:
                preserved[
                    (row.get("Category", ""), row.get("Index", ""), row.get("Original", ""))
                ] = translated
    return preserved


def selected_translation(
    category: str,
    index: int,
    original: str,
    preserved: dict[tuple[str, str, str], str],
    lookup: dict[str, str],
) -> str:
    return preserved.get((category, str(index), original), lookup.get(original, ""))


def decode_field(raw: bytes, label: str) -> str:
    try:
        return raw.decode("shift_jis", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label}: invalid Shift-JIS") from exc


def extract_fixed(
    data: bytes,
    spec: FixedTextSpec,
    preserved: dict[tuple[str, str, str], str],
    lookup: dict[str, str],
) -> list[dict[str, str | int]]:
    if data[:8] != spec.signature:
        raise ValueError(f"{spec.table}: unexpected signature {data[:8]!r}")
    count, table_offset = struct.unpack_from("<II", data, 8)
    if table_offset + count * spec.record_size > len(data):
        raise ValueError(f"{spec.table}: fixed array exceeds record")

    rows: list[dict[str, str | int]] = []
    for index in range(count):
        record_offset = table_offset + index * spec.record_size
        text_offset = record_offset + spec.text_offset
        field = data[text_offset : text_offset + spec.text_size]
        raw = field.split(b"\0", 1)[0]
        if not raw:
            continue
        original = decode_field(raw, f"{spec.table}[{index}]")
        rows.append(
            {
                "File Path": f"tbldata/{spec.table}",
                "Category": spec.category,
                "Index": index,
                "Record Offset": f"0x{record_offset:X}",
                "Offset": f"0x{text_offset:X}",
                "Field Size": spec.text_size,
                "Original Bytes": len(raw),
                "Original": original,
                "Translated": selected_translation(
                    spec.category, index, original, preserved, lookup
                ),
            }
        )
    return rows


def extract_pointer_text(
    data: bytes,
    spec: PointerTextSpec,
    preserved: dict[tuple[str, str, str], str],
    lookup: dict[str, str],
) -> list[dict[str, str | int]]:
    if data[:8] != spec.signature:
        raise ValueError(f"{spec.table}: unexpected signature {data[:8]!r}")
    count, table_offset = struct.unpack_from("<II", data, 8)
    if table_offset + count * spec.record_size > len(data):
        raise ValueError(f"{spec.table}: pointer array exceeds record")

    rows: list[dict[str, str | int]] = []
    for index in range(count):
        record_offset = table_offset + index * spec.record_size
        text_offset = struct.unpack_from(
            "<I", data, record_offset + spec.pointer_offset
        )[0]
        field_size = struct.unpack_from(
            "<I", data, record_offset + spec.size_offset
        )[0]
        if text_offset + field_size > len(data):
            raise ValueError(f"{spec.table}[{index}]: text field exceeds record")
        field = data[text_offset : text_offset + field_size]
        raw = field.rstrip(b"\0")
        if not raw:
            continue
        original = decode_field(raw, f"{spec.table}[{index}] description")
        rows.append(
            {
                "File Path": f"tbldata/{spec.table}",
                "Category": spec.category,
                "Index": index,
                "Record Offset": f"0x{record_offset:X}",
                "Offset": f"0x{text_offset:X}",
                "Field Size": field_size,
                "Original Bytes": len(raw),
                "Original": original,
                "Translated": selected_translation(
                    spec.category, index, original, preserved, lookup
                ),
            }
        )
    return rows


def audit_tsqv() -> tuple[int, int, list[dict[str, str]]]:
    existing = {
        (
            row["File Path"],
            int(row["Index"]),
            int(row["Offset"]),
            row["Original"],
        )
        for row in read_rows(WORKSPACE / "tsqv_translation.csv")
    }
    total = 0
    missing: list[dict[str, str]] = []
    record_count = 0
    for pack_path in sorted(ORIGINAL_SCPACK.glob("*.res")):
        archive = pack_path.read_bytes()
        for record_name, record_offset, record_size in parse_resc(archive):
            record = archive[record_offset : record_offset + record_size]
            if not record.startswith(b"TSQV1.10"):
                continue
            record_count += 1
            file_path = f"scpack/{pack_path.name}/{record_name}"
            for row in extract_tsqv_record(record):
                total += 1
                key = (
                    file_path,
                    int(row["Index"]),
                    int(row["Offset"]),
                    row["Original"],
                )
                if key not in existing:
                    missing.append(
                        {
                            "File Path": file_path,
                            "Index": str(row["Index"]),
                            "Offset": str(row["Offset"]),
                            "Original": row["Original"],
                            "Translated": "",
                        }
                    )
    return record_count, total, missing


def main() -> None:
    container = ORIGINAL_TBLDATA.read_bytes()
    record_headers = {
        item["name"].lower(): item for item in parse_res_header(container)
    }
    lookup = translation_lookup()
    preserved = preserved_output_translations()

    outputs: list[tuple[Path, list[dict[str, str | int]]]] = []
    all_rows: list[dict[str, str | int]] = []
    for spec in FIXED_SPECS:
        header = record_headers[spec.table]
        start = header["offset"]
        data = container[start : start + header["size"]]
        rows = extract_fixed(data, spec, preserved, lookup)
        output_name = f"{spec.table}_translation.csv"
        outputs.append((WORKSPACE / output_name, rows))
        all_rows.extend(rows)

    for spec in POINTER_SPECS:
        header = record_headers[spec.table]
        start = header["offset"]
        data = container[start : start + header["size"]]
        rows = extract_pointer_text(data, spec, preserved, lookup)
        output_name = f"{spec.table}_description_translation.csv"
        outputs.append((WORKSPACE / output_name, rows))
        all_rows.extend(rows)

    for output, rows in outputs:
        write_rows(output, rows)
        translated = sum(bool(str(row["Translated"]).strip()) for row in rows)
        print(f"{output.name}: {len(rows)} rows, prefilled {translated}")

    master = WORKSPACE / "missing_fixed_text_translation.csv"
    write_rows(master, all_rows)

    record_count, tsqv_total, missing_tsqv = audit_tsqv()
    tsqv_missing_path = WORKSPACE / "missing_tsqv_text_translation.csv"
    with tsqv_missing_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["File Path", "Index", "Offset", "Original", "Translated"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(missing_tsqv)

    report_path = WORKSPACE / "missing_text_extraction_report.csv"
    report_rows = []
    for output, rows in outputs:
        report_rows.append(
            {
                "Source": output.name,
                "Extracted": len(rows),
                "Prefilled": sum(bool(str(row["Translated"]).strip()) for row in rows),
                "Needs Translation": sum(
                    not bool(str(row["Translated"]).strip()) for row in rows
                ),
            }
        )
    report_rows.append(
        {
            "Source": f"TSQV ({record_count} records)",
            "Extracted": tsqv_total,
            "Prefilled": tsqv_total - len(missing_tsqv),
            "Needs Translation": len(missing_tsqv),
        }
    )
    with report_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["Source", "Extracted", "Prefilled", "Needs Translation"],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"Unified missing fixed text: {len(all_rows)} rows -> {master}")
    print(f"TSQV missed rows: {len(missing_tsqv)} -> {tsqv_missing_path}")
    print(f"Coverage report: {report_path}")


if __name__ == "__main__":
    main()
