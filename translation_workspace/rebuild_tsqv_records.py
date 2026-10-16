import csv
import hashlib
import struct
import sys
from pathlib import Path

from extract_tsqv import CSV_FIELDS, parse_resc
from in_place_patcher import (
    CUSTOM_ASCII_PUNCTUATION,
    collect_native_sjis_codes,
    get_sjis_safe_codes,
    normalize_runtime_text,
)
from name_input_config import NAME_INPUT_CHARS


MANIFEST_FIELDS = [
    "File Path",
    "Original Size",
    "Rebuilt Size",
    "Size Delta",
    "Translation Count",
    "SHA256",
]


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames != CSV_FIELDS:
            raise ValueError(
                f"{path}: unexpected columns {reader.fieldnames!r}; "
                f"expected {CSV_FIELDS!r}"
            )
        return list(reader)


def find_resc_record(data, target_name):
    for name, offset, size in parse_resc(data):
        if name.lower() == target_name.lower():
            return data[offset : offset + size]
    raise KeyError(target_name)


def build_character_mapping(project_root, table_rows, tsqv_rows):
    # Keep every encoder in lockstep with in_place_patcher.py.  Completed
    # fixed-name CSVs participate in the font map; incomplete CSVs do not.
    workspace = project_root / "translation_workspace"
    fixed_rows = []
    for csv_name in (
        "wpdttbl_translation.csv",
        "mnstbl_translation.csv",
        "pmprmtbl_translation.csv",
        "mgdttbl_translation.csv",
        "uidttbl_translation.csv",
        "uitmtbl_translation.csv",
        "sidttbl_translation.csv",
        "amdttbl_translation.csv",
        "magictbl_translation.csv",
        "mmgtbl_translation.csv",
        "sitmtbl_translation.csv",
        "magictbl_description_translation.csv",
        "sitmtbl_description_translation.csv",
        "uitmtbl_description_translation.csv",
        "evscript_text/evscript_translation.csv",
    ):
        csv_path = workspace / csv_name
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            candidate_rows = list(csv.DictReader(csv_file))
        if candidate_rows and all(
            row.get("Translated", "").strip() for row in candidate_rows
        ):
            fixed_rows.extend(candidate_rows)

    selected_texts = []
    korean_chars = []
    for row in table_rows + tsqv_rows + fixed_rows:
        text = normalize_runtime_text(
            row.get("Translated", "") or row.get("Original", "")
        )
        selected_texts.append(text)
        for char in text:
            if 0xAC00 <= ord(char) <= 0xD7A3 and char not in korean_chars:
                korean_chars.append(char)
    for char in NAME_INPUT_CHARS:
        if char not in korean_chars:
            korean_chars.append(char)
    custom_chars = korean_chars + list(CUSTOM_ASCII_PUNCTUATION)

    original_tbldata = (
        project_root
        / "Original/PSP_GAME/USRDIR/Resource/tbldata/tbldata.res"
    ).read_bytes()
    original_fonttbl = find_resc_record(original_tbldata, "fonttbl")
    if original_fonttbl[:8] != b"FTTV1.00":
        raise ValueError("unexpected original fonttbl signature")
    _, double_count, _, double_offset = struct.unpack_from(
        "<HHHH", original_fonttbl, 8
    )

    original_codes = {
        original_fonttbl[double_offset + index * 2 : double_offset + index * 2 + 2]
        for index in range(double_count)
    }
    native_codes = collect_native_sjis_codes(selected_texts)
    custom_codes = get_sjis_safe_codes(
        len(custom_chars), original_codes | native_codes
    )
    if len(custom_codes) != len(custom_chars):
        raise RuntimeError("could not allocate enough collision-free custom codes")

    available_tiles = []
    for tile_index in range(62, min(double_count, 32 * 32)):
        original_code = original_fonttbl[
            double_offset + tile_index * 2 : double_offset + tile_index * 2 + 2
        ]
        if original_code not in native_codes:
            available_tiles.append(tile_index)
    if len(custom_chars) > len(available_tiles):
        raise RuntimeError(
            f"{len(custom_chars)} custom characters exceed "
            f"{len(available_tiles)} safe font tiles"
        )

    # Confirm that step 2 installed the exact mapping this encoder will use.
    patched_tbldata = (
        project_root / "PSP_GAME/USRDIR/Resource/tbldata/tbldata.res"
    ).read_bytes()
    patched_fonttbl = find_resc_record(patched_tbldata, "fonttbl")
    for char, code, tile_index in zip(
        custom_chars, custom_codes, available_tiles
    ):
        installed = patched_fonttbl[
            double_offset + tile_index * 2 : double_offset + tile_index * 2 + 2
        ]
        if installed != code:
            raise RuntimeError(
                f"installed font mapping mismatch for {char!r} at tile {tile_index}"
            )

    return dict(zip(custom_chars, custom_codes))


def hybrid_encode_strict(text, char_to_sjis):
    text = normalize_runtime_text(text)
    encoded = bytearray()
    for char in text:
        if char in char_to_sjis:
            encoded.extend(char_to_sjis[char])
        else:
            try:
                encoded.extend(char.encode("shift_jis", errors="strict"))
            except UnicodeEncodeError as exc:
                raise ValueError(f"character cannot be encoded: {char!r}") from exc
    return bytes(encoded)


def parse_tsqv_slots(record_data):
    if record_data[:8] != b"TSQV1.10" or len(record_data) < 16:
        raise ValueError("not a complete TSQV1.10 record")

    instruction_count, instruction_offset, index_offset, data_offset = (
        struct.unpack_from("<HHHH", record_data, 8)
    )
    if instruction_offset != 0x10:
        raise ValueError(f"unexpected instruction offset {instruction_offset:#x}")
    if index_offset != instruction_offset + instruction_count * 6:
        raise ValueError("instruction and index sections are not contiguous")
    if not (index_offset <= data_offset <= len(record_data)):
        raise ValueError("invalid index/data boundary")
    if (data_offset - index_offset) % 4:
        raise ValueError("string index is not 4-byte aligned")

    slots = []
    slot_count = (data_offset - index_offset) // 4
    expected_offset = data_offset
    for slot_index in range(slot_count):
        entry_offset = index_offset + slot_index * 4
        string_offset, slot_size = struct.unpack_from(
            "<HH", record_data, entry_offset
        )
        if string_offset != expected_offset:
            raise ValueError(
                f"slot {slot_index} is not contiguous: "
                f"{string_offset:#x} != {expected_offset:#x}"
            )
        if string_offset % 2 or slot_size % 2 or slot_size == 0:
            raise ValueError(f"slot {slot_index} violates 2-byte alignment")
        slot_end = string_offset + slot_size
        if slot_end > len(record_data):
            raise ValueError(f"slot {slot_index} exceeds record size")
        slots.append((entry_offset, string_offset, slot_size))
        expected_offset = slot_end
    if expected_offset != len(record_data):
        raise ValueError("TSQV data does not end at the record boundary")
    return data_offset, slots


def rebuild_record(record_data, translations, char_to_sjis, label):
    data_offset, slots = parse_tsqv_slots(record_data)
    rebuilt_header = bytearray(record_data[:data_offset])
    rebuilt_data = bytearray()

    for slot_index, (entry_offset, string_offset, slot_size) in enumerate(slots):
        original_slot = record_data[string_offset : string_offset + slot_size]
        if slot_index in translations:
            row = translations[slot_index]
            payload = original_slot.rstrip(b"\x00")
            try:
                original_text = payload.decode("shift_jis", errors="strict")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"{label}: translated slot {slot_index} is not Shift-JIS text"
                ) from exc
            if original_text != row["Original"]:
                raise ValueError(
                    f"{label}: source mismatch at slot {slot_index}: "
                    f"{original_text!r} != {row['Original']!r}"
                )
            translated = row["Translated"]
            if not translated.strip():
                raise ValueError(f"{label}: empty translation at slot {slot_index}")
            rebuilt_slot = hybrid_encode_strict(translated, char_to_sjis) + b"\x00"
            if len(rebuilt_slot) % 2:
                rebuilt_slot += b"\x00"
        else:
            rebuilt_slot = original_slot

        rebuilt_offset = data_offset + len(rebuilt_data)
        if rebuilt_offset > 0xFFFF or len(rebuilt_slot) > 0xFFFF:
            raise ValueError(f"{label}: rebuilt slot exceeds TSQV 16-bit limits")
        struct.pack_into(
            "<HH", rebuilt_header, entry_offset, rebuilt_offset, len(rebuilt_slot)
        )
        rebuilt_data.extend(rebuilt_slot)

    rebuilt = bytes(rebuilt_header + rebuilt_data)
    if len(rebuilt) > 0xFFFF:
        raise ValueError(f"{label}: rebuilt record exceeds 65,535 bytes")
    return rebuilt


def main():
    workspace = Path(__file__).resolve().parent
    project_root = workspace.parent
    source_root = project_root / "Original/PSP_GAME/USRDIR/Resource/scpack"
    output_root = workspace / "tsqv_rebuilt" / "scpack"
    manifest_path = workspace / "tsqv_rebuilt" / "manifest.csv"

    table_rows = read_csv(workspace / "total_translation.csv")
    tsqv_rows = read_csv(workspace / "tsqv_translation.csv")
    char_to_sjis = build_character_mapping(project_root, table_rows, tsqv_rows)

    translations_by_record = {}
    for row in tsqv_rows:
        parts = row["File Path"].replace("\\", "/").split("/")
        if len(parts) != 3 or parts[0] != "scpack":
            raise ValueError(f"invalid TSQV path: {row['File Path']!r}")
        record_key = (parts[1], parts[2])
        slot_index = int(row["Index"])
        record_translations = translations_by_record.setdefault(record_key, {})
        if slot_index in record_translations:
            raise ValueError(
                f"duplicate TSQV slot: {parts[1]}/{parts[2]} index {slot_index}"
            )
        record_translations[slot_index] = row

    manifest_rows = []
    rebuilt_translation_count = 0
    for pack_name in sorted({key[0] for key in translations_by_record}):
        archive = (source_root / pack_name).read_bytes()
        records = {name: (offset, size) for name, offset, size in parse_resc(archive)}
        record_names = sorted(
            key[1] for key in translations_by_record if key[0] == pack_name
        )
        for record_name in record_names:
            if record_name not in records:
                raise KeyError(f"{pack_name}: missing record {record_name}")
            record_offset, record_size = records[record_name]
            original = archive[record_offset : record_offset + record_size]
            translations = translations_by_record[(pack_name, record_name)]
            label = f"scpack/{pack_name}/{record_name}"
            rebuilt = rebuild_record(original, translations, char_to_sjis, label)

            output_path = output_root / pack_name / f"{record_name}.bin"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(rebuilt)
            rebuilt_translation_count += len(translations)
            manifest_rows.append(
                {
                    "File Path": label,
                    "Original Size": len(original),
                    "Rebuilt Size": len(rebuilt),
                    "Size Delta": len(rebuilt) - len(original),
                    "Translation Count": len(translations),
                    "SHA256": hashlib.sha256(rebuilt).hexdigest(),
                }
            )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    if rebuilt_translation_count != len(tsqv_rows):
        raise RuntimeError(
            f"rebuilt {rebuilt_translation_count} translations; "
            f"expected {len(tsqv_rows)}"
        )

    print(f"Custom font codes loaded: {len(char_to_sjis)}")
    print(f"Rebuilt TSQV records: {len(manifest_rows)}")
    print(f"Inserted translations: {rebuilt_translation_count}")
    print(f"Output root: {output_root}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
