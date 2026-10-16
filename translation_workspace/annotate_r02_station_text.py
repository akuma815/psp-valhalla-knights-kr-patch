from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WORKSPACE = Path(__file__).resolve().parent
EXTRACTED = WORKSPACE / "r02_battle_ui_extracted"
TEXTURES = EXTRACTED / "textures"
CSV_PATH = EXTRACTED / "station_text_translation.csv"


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    rows = load_rows()
    for texture in sorted({row["Texture"] for row in rows}):
        image = Image.open(TEXTURES / f"{texture}_dark.png").convert("RGB")
        draw = ImageDraw.Draw(image)
        texture_rows = [row for row in rows if row["Texture"] == texture]
        for row in texture_rows:
            x = int(row["X"])
            y = int(row["Y"])
            width = int(row["Width"])
            height = int(row["Height"])
            color = (255, 70, 70) if row["Confidence"] == "HIGH" else (255, 190, 50)
            draw.rectangle((x, y, x + width - 1, y + height - 1), outline=color)
            draw.text((x + 1, max(0, y - 9)), row["ID"], fill=color)

        scale = 2 if texture == "station0" else 4
        image = image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.NEAREST,
        )
        output = TEXTURES / f"{texture}_text_map.png"
        image.save(output)
        print(f"Wrote {output}")

    print(f"Mapped {len(rows)} Japanese text regions")


if __name__ == "__main__":
    main()
