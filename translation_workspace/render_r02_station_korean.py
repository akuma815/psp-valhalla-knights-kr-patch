from __future__ import annotations

import csv
import struct
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
EXTRACTED = WORKSPACE / "r02_battle_ui_extracted"
TEXTURES = EXTRACTED / "textures"
CSV_PATH = EXTRACTED / "station_text_translation.csv"
FONT_PATH = ROOT / "font.ttf"
GIMCONV = ROOT / "tool" / "GimConv" / "GimConv.exe"

STATUS_COLORS = {
    "S2_017": (178, 72, 220, 255),
    "S2_018": (178, 220, 166, 255),
    "S2_019": (82, 112, 255, 255),
    "S2_020": (230, 224, 75, 255),
    "S2_021": (139, 220, 225, 255),
    "S2_022": (220, 218, 210, 255),
}

# keyhlps1 in gsprite.res crops these menu labels as a 5 x 2 grid of
# independent 48 x 24 cells.  Editing only the visible Japanese ink bounds
# can cross a neighbouring crop and erase or displace another command.
BATTLE_MENU_CELLS = {
    f"S2_{item:03d}": (
        ((item - 7) % 5) * 48,
        184 + ((item - 7) // 5) * 24,
        48,
        24,
    )
    for item in range(7, 17)
}


def font_size_for(row: dict[str, str]) -> int:
    if row["Texture"] == "station0":
        return 14
    item = row["ID"]
    if item in {"S2_010", "S2_011", "S2_013", "S2_014", "S2_016", "S2_023", "S2_024"}:
        return 12
    if item in {"S2_007", "S2_008", "S2_009"}:
        return 10
    return 9


def measure_lines(font: ImageFont.FreeTypeFont, lines: list[str]) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    boxes = [font.getbbox(line) for line in lines]
    widths = [box[2] - box[0] for box in boxes]
    heights = [box[3] - box[1] for box in boxes]
    line_gap = 1 if len(lines) > 1 else 0
    return max(widths), sum(heights) + line_gap * (len(lines) - 1), boxes


def render_row(image: Image.Image, row: dict[str, str], report: list[dict[str, str | int]]) -> None:
    x, y, width, height = (
        int(row["X"]),
        int(row["Y"]),
        int(row["Width"]),
        int(row["Height"]),
    )
    expected_cell = BATTLE_MENU_CELLS.get(row["ID"])
    if expected_cell is not None and (x, y, width, height) != expected_cell:
        raise ValueError(
            f"{row['ID']} must use sprite cell {expected_cell}, "
            f"not {(x, y, width, height)}"
        )
    text = row["Translated"].replace("\\n", "\n").strip()
    if not text:
        raise ValueError(f"blank translation: {row['ID']}")

    lines = text.split("\n")
    font_size = font_size_for(row)
    font = ImageFont.truetype(str(FONT_PATH), font_size)
    text_width, text_height, boxes = measure_lines(font, lines)
    if text_width > width or text_height > height:
        raise ValueError(
            f"{row['ID']} does not fit: {text_width}x{text_height} > {width}x{height}"
        )

    transparent = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste(transparent, (x, y))
    draw = ImageDraw.Draw(image)
    color = STATUS_COLORS.get(row["ID"], (232, 232, 232, 255))
    cursor_y = y + (height - text_height) // 2
    for line, box in zip(lines, boxes):
        line_width = box[2] - box[0]
        line_height = box[3] - box[1]
        cursor_x = x + (width - line_width) // 2 - box[0]
        baseline_y = cursor_y - box[1]
        draw.text((cursor_x + 1, baseline_y + 1), line, font=font, fill=(0, 0, 0, 210))
        draw.text((cursor_x, baseline_y), line, font=font, fill=color)
        cursor_y += line_height + 1

    report.append(
        {
            "ID": row["ID"],
            "Texture": row["Texture"],
            "Translated": text.replace("\n", "\\n"),
            "Font Size": font_size,
            "Measured Width": text_width,
            "Measured Height": text_height,
            "Box Width": width,
            "Box Height": height,
            "Fit": "PASS",
        }
    )


def compile_gim(texture: str, png_path: Path, size: tuple[int, int]) -> Path:
    output = TEXTURES / f"{texture}_korean_compiled.gim"
    command = [
        str(GIMCONV),
        str(png_path),
        "--format_style", "psp",
        "--format_endian", "little",
        "--image_format", "index8",
        "--palette_format", "rgba8888",
        "--pixel_order", "faster",
        "--output_palette", "on",
        "-s", f"{size[0]},{size[1]}",
        "-o", str(output),
    ]
    subprocess.run(command, check=True, cwd=GIMCONV.parent)
    if not output.exists():
        raise RuntimeError(f"GimConv did not create {output}")
    return output


def merge_picture_block(texture: str, compiled_path: Path) -> Path:
    original_path = TEXTURES / f"{texture}.gim"
    original = bytearray(original_path.read_bytes())
    compiled = compiled_path.read_bytes()
    picture_offset = 0x20

    original_header = struct.unpack_from("<IIII", original, picture_offset)
    compiled_header = struct.unpack_from("<IIII", compiled, picture_offset)
    if original_header[0] != 3 or compiled_header[0] != 3:
        raise ValueError(f"{texture}: unexpected GIM picture block type")
    original_size = original_header[1]
    compiled_size = compiled_header[1]
    if original_size != compiled_size:
        raise ValueError(
            f"{texture}: picture block mismatch {compiled_size} != {original_size}"
        )

    picture_end = picture_offset + original_size
    if picture_end > len(original) or picture_offset + compiled_size > len(compiled):
        raise ValueError(f"{texture}: picture block exceeds its GIM")

    prefix = bytes(original[:picture_offset])
    suffix = bytes(original[picture_end:])
    original[picture_offset:picture_end] = compiled[
        picture_offset : picture_offset + compiled_size
    ]
    if bytes(original[:picture_offset]) != prefix or bytes(original[picture_end:]) != suffix:
        raise RuntimeError(f"{texture}: bytes outside the picture block changed")

    output = TEXTURES / f"{texture}_korean.gim"
    output.write_bytes(original)
    if output.stat().st_size != original_path.stat().st_size:
        raise ValueError(f"{texture}: merged GIM size changed")
    return output


def main() -> None:
    if not FONT_PATH.exists():
        raise FileNotFoundError(FONT_PATH)
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 25:
        raise ValueError(f"expected 25 rows, found {len(rows)}")

    report: list[dict[str, str | int]] = []
    for texture in ("station0", "station2"):
        source = TEXTURES / f"{texture}.png"
        image = Image.open(source).convert("RGBA")
        for row in rows:
            if row["Texture"] == texture:
                render_row(image, row, report)

        png_path = TEXTURES / f"{texture}_korean.png"
        image.save(png_path)
        dark = Image.new("RGBA", image.size, (35, 35, 35, 255))
        dark.alpha_composite(image)
        dark.convert("RGB").save(TEXTURES / f"{texture}_korean_dark.png")

        indexed = image.quantize(
            colors=256,
            method=Image.Quantize.FASTOCTREE,
            dither=Image.Dither.NONE,
        )
        indexed_path = TEXTURES / f"{texture}_korean_indexed.png"
        indexed.save(indexed_path)
        compiled_path = compile_gim(texture, indexed_path, image.size)
        gim_path = merge_picture_block(texture, compiled_path)
        original_gim = TEXTURES / f"{texture}.gim"
        if gim_path.stat().st_size != original_gim.stat().st_size:
            raise ValueError(
                f"{texture} GIM size mismatch: {gim_path.stat().st_size} != "
                f"{original_gim.stat().st_size}"
            )

    fields = [
        "ID", "Texture", "Translated", "Font Size", "Measured Width",
        "Measured Height", "Box Width", "Box Height", "Fit",
    ]
    with (EXTRACTED / "render_validation.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report)

    counts = Counter(row["Fit"] for row in report)
    print(f"Rendered rows: {len(report)}")
    print(f"Fit results: {dict(counts)}")


if __name__ == "__main__":
    main()
