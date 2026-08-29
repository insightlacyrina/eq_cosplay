#!/usr/bin/env python3
"""Build EchoCR-styled app / menu-bar icons from the bundled FangXinShu font."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "assets" / "fonts" / "fang-xin-shu.ttf"
OUT = ROOT / "assets" / "icons"
BG = (11, 13, 17, 255)
GOLD = (212, 162, 74, 255)
WHITE = (255, 255, 255, 255)


def _require_pil():
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "-q"])
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    return __import__("PIL.Image", fromlist=["Image"]).Image  # dummy


def load_font(size: int):
    from PIL import ImageFont

    if FONT.is_file():
        return ImageFont.truetype(str(FONT), size=size)
    return ImageFont.load_default()


def draw_app_icon(size: int = 1024):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(size * 0.06)
    radius = int(size * 0.08)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=BG,
    )
    inner = pad + int(size * 0.10)
    draw.rounded_rectangle(
        [inner, inner, size - inner, size - inner],
        radius=max(4, radius // 3),
        outline=GOLD,
        width=max(2, size // 64),
    )
    font = load_font(int(size * 0.38))
    text = "EQ"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1] - size * 0.02
    draw.text((x, y), text, font=font, fill=GOLD)
    return img


def draw_menubar(size: int = 44):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    inset = max(1, size // 16)
    draw.rectangle(
        [inset, inset, size - inset - 1, size - inset - 1],
        outline=WHITE,
        width=max(1, size // 22),
    )
    font = load_font(int(size * 0.42))
    text = "EQ"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=WHITE)
    return img


def write_icns(png_1024: Path, dest: Path) -> None:
    iconset = dest.with_suffix(".iconset")
    if iconset.exists():
        import shutil

        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    mapping = {
        16: "icon_16x16.png",
        32: "icon_16x16@2x.png",
        32: "icon_32x32.png",
        64: "icon_32x32@2x.png",
        128: "icon_128x128.png",
        256: "icon_128x128@2x.png",
        256: "icon_256x256.png",
        512: "icon_256x256@2x.png",
        512: "icon_512x512.png",
        1024: "icon_512x512@2x.png",
    }
    # last assignment wins for duplicate keys; write each needed size explicitly
    from PIL import Image

    src = Image.open(png_1024)
    jobs = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for px, name in jobs:
        src.resize((px, px), Image.Resampling.LANCZOS).save(iconset / name)
    subprocess.check_call(["iconutil", "-c", "icns", str(iconset), "-o", str(dest)])


def write_ico(png_1024: Path, dest: Path) -> None:
    from PIL import Image

    src = Image.open(png_1024)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    src.save(dest, format="ICO", sizes=sizes)


def main() -> None:
    _require_pil()
    OUT.mkdir(parents=True, exist_ok=True)
    app = draw_app_icon(1024)
    app_path = OUT / "app.png"
    app.save(app_path)
    menubar = draw_menubar(44)
    menubar.save(OUT / "menubar.png")
    draw_menubar(22).save(OUT / "menubarTemplate.png")
    icns = ROOT / "packaging" / "EQCosplay.icns"
    ico = ROOT / "packaging" / "EQCosplay.ico"
    if sys.platform == "darwin":
        try:
            write_icns(app_path, icns)
        except Exception as exc:
            print(f"[WARN] icns: {exc}", file=sys.stderr)
            app.save(icns.with_suffix(".png"))
    try:
        write_ico(app_path, ico)
    except Exception as exc:
        print(f"[WARN] ico: {exc}", file=sys.stderr)
    print(f"[OK] icons → {OUT}")


if __name__ == "__main__":
    main()
