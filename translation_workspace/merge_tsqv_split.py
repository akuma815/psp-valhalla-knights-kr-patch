import csv
import shutil
from pathlib import Path


FIELDS = ["File Path", "Index", "Offset", "Original", "Translated"]


def row_key(row):
    return tuple(row[field] for field in FIELDS[:4])


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames != FIELDS:
            raise ValueError(
                f"{path}: unexpected columns {reader.fieldnames!r}; expected {FIELDS!r}"
            )
        return list(reader)


def main():
    workspace = Path(__file__).resolve().parent
    master_path = workspace / "tsqv_translation.csv"
    split_dir = workspace / "tsqv_translation_split"
    backup_path = workspace / "backups" / "tsqv_translation_before_split_merge.csv"

    master_rows = read_csv(master_path)
    split_paths = sorted(split_dir.glob("tsqv_translation_part_*.csv"))
    if not split_paths:
        raise RuntimeError(f"no split CSV files found in {split_dir}")

    translations = {}
    duplicate_keys = []
    for split_path in split_paths:
        for row in read_csv(split_path):
            key = row_key(row)
            if key in translations:
                duplicate_keys.append(key)
            translations[key] = row["Translated"]

    if duplicate_keys:
        raise RuntimeError(f"duplicate split keys: {len(duplicate_keys)}")

    master_keys = {row_key(row) for row in master_rows}
    split_keys = set(translations)
    missing = master_keys - split_keys
    extra = split_keys - master_keys
    empty = [key for key, text in translations.items() if not text.strip()]
    if missing or extra or empty:
        raise RuntimeError(
            "split validation failed: "
            f"missing={len(missing)}, extra={len(extra)}, empty={len(empty)}"
        )

    for row in master_rows:
        row["Translated"] = translations[row_key(row)]

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not backup_path.exists():
        shutil.copy2(master_path, backup_path)

    temporary_path = master_path.with_suffix(".csv.tmp")
    with temporary_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(master_rows)
    temporary_path.replace(master_path)

    print(f"Split files merged: {len(split_paths)}")
    print(f"Translations merged: {len(master_rows)}")
    print(f"Backup: {backup_path}")
    print(f"Output: {master_path}")


if __name__ == "__main__":
    main()
