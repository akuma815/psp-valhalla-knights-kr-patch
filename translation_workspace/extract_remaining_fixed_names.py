from __future__ import annotations

import csv
import struct
from dataclasses import dataclass
from pathlib import Path

from in_place_patcher import parse_res_header


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
ORIGINAL_TBLDATA = (
    ROOT / "Original/PSP_GAME/USRDIR/Resource/tbldata/tbldata.res"
)


@dataclass(frozen=True)
class NameSpec:
    table: str
    signature: bytes
    record_size: int
    name_size: int
    category: str


SPECS = (
    NameSpec("pmprmtbl", b"PMTV1.01", 72, 16, "프리셋 캐릭터명"),
    NameSpec("mgdttbl", b"MDTV1.25", 24, 16, "마법명"),
    NameSpec("uidttbl", b"UDTV1.06", 28, 20, "사용 아이템명"),
    NameSpec("uitmtbl", b"UITV1.11", 32, 20, "소모품명"),
    NameSpec("sidttbl", b"SDTV1.00", 24, 24, "특수 아이템명"),
)


def main() -> None:
    container = ORIGINAL_TBLDATA.read_bytes()
    records = {item["name"].lower(): item for item in parse_res_header(container)}

    total = 0
    for spec in SPECS:
        record = records[spec.table]
        start = record["offset"]
        data = container[start : start + record["size"]]
        if data[:8] != spec.signature:
            raise ValueError(f"{spec.table}: unexpected signature {data[:8]!r}")
        count, table_offset = struct.unpack_from("<II", data, 8)
        if table_offset + count * spec.record_size > len(data):
            raise ValueError(f"{spec.table}: name array exceeds record")

        rows = []
        for index in range(count):
            record_offset = table_offset + index * spec.record_size
            field = data[record_offset : record_offset + spec.name_size]
            raw = field.split(b"\0", 1)[0]
            try:
                original = raw.decode("shift_jis")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"{spec.table}[{index}]: invalid Shift-JIS name"
                ) from exc
            rows.append(
                {
                    "File Path": f"tbldata/{spec.table}",
                    "Category": spec.category,
                    "Index": index,
                    "Record Offset": f"0x{record_offset:X}",
                    "Name Offset": f"0x{record_offset:X}",
                    "Field Size": spec.name_size,
                    "Original Bytes": len(raw),
                    "Original": original,
                    "Translated": "",
                }
            )

        output = WORKSPACE / f"{spec.table}_translation.csv"
        with output.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        total += len(rows)
        print(f"{spec.table}: {len(rows)} rows -> {output}")

    print(f"Extracted remaining fixed names: {total}")


if __name__ == "__main__":
    main()
