from __future__ import annotations

import csv
import struct
import subprocess
from pathlib import Path

from PIL import Image

from in_place_patcher import parse_res_header


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "translation_workspace"
ORIGINAL_RESOURCE = ROOT / "Original" / "PSP_GAME" / "USRDIR" / "Resource"
OUTPUT = WORKSPACE / "r02_battle_ui_extracted"
GIMCONV = ROOT / "tool" / "GimConv" / "GimConv.exe"


def records_by_name(container: bytes) -> dict[str, dict]:
    return {record["name"]: record for record in parse_res_header(container)}


def record_bytes(container: bytes, record: dict) -> bytes:
    start = record["offset"]
    return container[start : start + record["size"]]


def sprite_texture_refs(data: bytes) -> tuple[int, list[str]]:
    if len(data) < 8:
        raise ValueError("sprite record is shorter than its header")
    sprite_count, texture_count = struct.unpack_from("<II", data, 0)
    names_end = 8 + texture_count * 8
    if names_end > len(data):
        raise ValueError("sprite texture-name array exceeds the record")
    names = []
    for index in range(texture_count):
        raw = data[8 + index * 8 : 16 + index * 8]
        names.append(raw.split(b"\0", 1)[0].decode("ascii"))
    return sprite_count, names


def main() -> None:
    if not GIMCONV.exists():
        raise FileNotFoundError(f"GimConv not found: {GIMCONV}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sprite_dir = OUTPUT / "sprite_definitions"
    texture_dir = OUTPUT / "textures"
    sprite_dir.mkdir(exist_ok=True)
    texture_dir.mkdir(exist_ok=True)

    gsprite_path = ORIGINAL_RESOURCE / "gsprite" / "gsprite.res"
    global_path = ORIGINAL_RESOURCE / "global" / "global.res"
    gsprite = gsprite_path.read_bytes()
    global_res = global_path.read_bytes()
    gsprite_records = records_by_name(gsprite)
    global_records = records_by_name(global_res)

    manifest_rows: list[dict[str, str | int]] = []
    referenced_textures: set[str] = set()

    for name in sorted(n for n in gsprite_records if n.startswith("btmens")):
        record = gsprite_records[name]
        data = record_bytes(gsprite, record)
        sprite_count, texture_refs = sprite_texture_refs(data)
        (sprite_dir / f"{name}.bin").write_bytes(data)
        referenced_textures.update(texture_refs)
        manifest_rows.append(
            {
                "kind": "sprite_definition",
                "name": name,
                "source": "gsprite/gsprite.res",
                "offset": f"0x{record['offset']:X}",
                "size": record["size"],
                "sprite_count": sprite_count,
                "texture_refs": ";".join(texture_refs),
                "output": f"sprite_definitions/{name}.bin",
            }
        )

    for name in sorted(referenced_textures):
        if name not in global_records:
            raise KeyError(f"referenced texture is absent from global.res: {name}")
        record = global_records[name]
        data = record_bytes(global_res, record)
        if not data.startswith(b"MIG.00.1PSP"):
            raise ValueError(f"{name} is not a PSP GIM record")
        gim_path = texture_dir / f"{name}.gim"
        png_path = texture_dir / f"{name}.png"
        gim_path.write_bytes(data)
        subprocess.run(
            [str(GIMCONV), str(gim_path), "-o", str(png_path)],
            check=True,
            cwd=GIMCONV.parent,
        )
        if not png_path.exists():
            raise RuntimeError(f"GimConv did not create {png_path}")

        rgba = Image.open(png_path).convert("RGBA")
        dark = Image.new("RGBA", rgba.size, (35, 35, 35, 255))
        dark.alpha_composite(rgba)
        dark_path = texture_dir / f"{name}_dark.png"
        dark.convert("RGB").save(dark_path)

        extra_outputs = [f"textures/{name}_dark.png"]
        if name == "station2":
            crop_box = (0, 176, rgba.width, rgba.height)
            crop = rgba.crop(crop_box)
            crop_path = texture_dir / "station2_battle_text_crop.png"
            crop.save(crop_path)

            crop_dark = Image.new("RGBA", crop.size, (35, 35, 35, 255))
            crop_dark.alpha_composite(crop)
            crop_dark = crop_dark.resize(
                (crop.width * 4, crop.height * 4), Image.Resampling.NEAREST
            )
            crop_dark_path = texture_dir / "station2_battle_text_crop_x4.png"
            crop_dark.convert("RGB").save(crop_dark_path)
            extra_outputs.extend(
                [
                    "textures/station2_battle_text_crop.png",
                    "textures/station2_battle_text_crop_x4.png",
                ]
            )
        manifest_rows.append(
            {
                "kind": "texture",
                "name": name,
                "source": "global/global.res",
                "offset": f"0x{record['offset']:X}",
                "size": record["size"],
                "sprite_count": "",
                "texture_refs": "",
                "output": "; ".join(
                    [f"textures/{name}.gim", f"textures/{name}.png"]
                    + extra_outputs
                ),
            }
        )

    manifest_path = OUTPUT / "manifest.csv"
    fieldnames = [
        "kind",
        "name",
        "source",
        "offset",
        "size",
        "sprite_count",
        "texture_refs",
        "output",
    ]
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Extracted {len(manifest_rows)} records to {OUTPUT}")
    print(f"Battle texture references: {', '.join(sorted(referenced_textures))}")


if __name__ == "__main__":
    main()
