from __future__ import annotations

import csv
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parent
MASTER = WORKSPACE / "missing_fixed_text_translation.csv"
TARGETS = (
    "amdttbl_translation.csv",
    "magictbl_translation.csv",
    "mmgtbl_translation.csv",
    "sitmtbl_translation.csv",
    "magictbl_description_translation.csv",
    "sitmtbl_description_translation.csv",
    "uitmtbl_description_translation.csv",
)
KEY_FIELDS = ("File Path", "Category", "Index", "Original")


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or ()), list(reader)


def key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row.get(field, "") for field in KEY_FIELDS)


def main() -> None:
    _, master_rows = read_rows(MASTER)
    if not master_rows or any(not row.get("Translated", "").strip() for row in master_rows):
        raise ValueError("master CSV is missing one or more translations")
    master = {key(row): row["Translated"].strip() for row in master_rows}
    if len(master) != len(master_rows):
        raise ValueError("master CSV contains duplicate keys")

    used: set[tuple[str, ...]] = set()
    for csv_name in TARGETS:
        path = WORKSPACE / csv_name
        fields, rows = read_rows(path)
        for row in rows:
            row_key = key(row)
            if row_key not in master:
                raise KeyError(f"{csv_name}: master row not found: {row_key}")
            row["Translated"] = master[row_key]
            used.add(row_key)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Synchronized {csv_name}: {len(rows)}/{len(rows)}")

    missing = set(master) - used
    if missing or len(used) != len(master_rows):
        raise ValueError(f"master coverage mismatch: used={len(used)}, missing={len(missing)}")
    print(f"Master coverage: {len(used)}/{len(master_rows)}")


if __name__ == "__main__":
    main()
