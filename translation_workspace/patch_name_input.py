from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path

from name_input_config import NAME_PAGE_ONE, NAME_PAGE_TWO
from rebuild_tsqv_records import build_character_mapping, read_csv


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
ORIGINAL_BOOT = ROOT / "Original/PSP_GAME/SYSDIR/BOOT.BIN"
ORIGINAL_EBOOT = ROOT / "Original/PSP_GAME/SYSDIR/EBOOT.BIN"
PATCHED_BOOT = ROOT / "PSP_GAME/SYSDIR/BOOT.BIN"
PATCHED_EBOOT = ROOT / "PSP_GAME/SYSDIR/EBOOT.BIN"
BACKUP_DIR = WORKSPACE / "backups/r03_name_input_before_patch"
OUTPUT_DIR = WORKSPACE / "name_input_rebuild"

PAGE_SIZE = 0xE0
PAGE_LAYOUTS = (
    ("가", 0x1FACFC, NAME_PAGE_ONE, "hiragana"),
    ("나", 0x1FADDC, NAME_PAGE_TWO, "katakana"),
)
ENGLISH_OFFSET = 0x1FAEBC


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_sjis(code: bytes) -> str | None:
    try:
        return code.decode("shift_jis")
    except UnicodeDecodeError:
        return None


def is_source_page_character(char: str | None, source_kind: str) -> bool:
    if not char or len(char) != 1:
        return False
    value = ord(char)
    if source_kind == "hiragana":
        return 0x3040 <= value <= 0x309F
    return 0x30A0 <= value <= 0x30FF


def main() -> None:
    original = ORIGINAL_BOOT.read_bytes()
    if len(original) <= ENGLISH_OFFSET + PAGE_SIZE:
        raise ValueError("BOOT.BIN is too small for the known name input arrays")

    table_rows = read_csv(WORKSPACE / "total_translation.csv")
    tsqv_rows = read_csv(WORKSPACE / "tsqv_translation.csv")
    char_to_sjis = build_character_mapping(ROOT, table_rows, tsqv_rows)

    missing = sorted(
        {char for _, _, chars, _ in PAGE_LAYOUTS for char in chars}
        - set(char_to_sjis)
    )
    if missing:
        raise ValueError(f"name input glyphs are missing from font map: {''.join(missing)}")
    patched = bytearray(original)
    english_before = original[ENGLISH_OFFSET : ENGLISH_OFFSET + PAGE_SIZE]
    report = []

    for page_name, page_offset, page_chars, source_kind in PAGE_LAYOUTS:
        positions = []
        for slot in range(PAGE_SIZE // 2):
            offset = page_offset + slot * 2
            code = original[offset : offset + 2]
            char = decode_sjis(code)
            if is_source_page_character(char, source_kind) or code == b"\x81\x7c":
                positions.append((slot, offset, code, char))

        if len(positions) != len(page_chars):
            raise ValueError(
                f"{page_name} page character cells {len(positions)} "
                f"!= configured syllables {len(page_chars)}"
            )

        for (slot, offset, old_code, old_char), new_char in zip(positions, page_chars):
            new_code = char_to_sjis[new_char]
            patched[offset : offset + 2] = new_code
            report.append(
                {
                    "Page": page_name,
                    "Slot": slot,
                    "BOOT Offset": f"0x{offset:X}",
                    "Original": old_char,
                    "Korean": new_char,
                    "Font Code": new_code.hex(" ").upper(),
                }
            )

    if patched[ENGLISH_OFFSET : ENGLISH_OFFSET + PAGE_SIZE] != english_before:
        raise RuntimeError("English name input page changed unexpectedly")
    if len(patched) != len(original):
        raise RuntimeError("BOOT.BIN size changed")

    allowed = set()
    for _, page_offset, _, _ in PAGE_LAYOUTS:
        allowed.update(range(page_offset, page_offset + PAGE_SIZE))
    unexpected = [
        index
        for index, (before, after) in enumerate(zip(original, patched))
        if before != after and index not in allowed
    ]
    if unexpected:
        raise RuntimeError(f"BOOT.BIN changed outside name arrays at {unexpected[0]:#x}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if PATCHED_BOOT.exists() and not (BACKUP_DIR / "BOOT.BIN").exists():
        shutil.copy2(PATCHED_BOOT, BACKUP_DIR / "BOOT.BIN")
    if PATCHED_EBOOT.exists() and not (BACKUP_DIR / "EBOOT.BIN").exists():
        shutil.copy2(PATCHED_EBOOT, BACKUP_DIR / "EBOOT.BIN")
    if not (BACKUP_DIR / "Original_BOOT.BIN").exists():
        shutil.copy2(ORIGINAL_BOOT, BACKUP_DIR / "Original_BOOT.BIN")
    if not (BACKUP_DIR / "Original_EBOOT.BIN").exists():
        shutil.copy2(ORIGINAL_EBOOT, BACKUP_DIR / "Original_EBOOT.BIN")

    patched_bytes = bytes(patched)
    PATCHED_BOOT.write_bytes(patched_bytes)
    # Commercial PSP discs normally contain an encrypted ~PSP EBOOT beside
    # the decrypted ELF BOOT.  PPSSPP starts EBOOT.BIN, so changing BOOT alone
    # leaves the original Japanese name-input arrays active.  PPSSPP accepts
    # the decrypted ELF at the EBOOT path; install the exact same patched ELF
    # there so the executable it actually loads contains the new arrays.
    PATCHED_EBOOT.write_bytes(patched_bytes)
    if PATCHED_EBOOT.read_bytes() != PATCHED_BOOT.read_bytes():
        raise RuntimeError("BOOT.BIN and EBOOT.BIN differ after installation")
    with (OUTPUT_DIR / "name_input_mapping.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=report[0].keys())
        writer.writeheader()
        writer.writerows(report)

    print(f"Korean name input cells: {len(report)} (81 + 82)")
    print("English page: unchanged")
    print(f"Original BOOT.BIN SHA-256: {sha256(original)}")
    print(f"Patched  BOOT.BIN SHA-256: {sha256(patched_bytes)}")
    print(f"Patched EBOOT.BIN SHA-256: {sha256(patched_bytes)} (decrypted ELF)")
    print(f"Mapping report: {OUTPUT_DIR / 'name_input_mapping.csv'}")


if __name__ == "__main__":
    main()
