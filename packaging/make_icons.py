#!/usr/bin/env python3
"""Build app / menu-bar / window icons from the artwork in assets/icons/source.png."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
SOURCE_STABLE = OUT / "source.png"


def _require_pil():
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "-q"])


def find_source() -> Path:
    candidates = [
        OUT / "theme-icon.png",
        ROOT / "theme-icon.png",
        SOURCE_STABLE,
        ROOT / "主题.png",
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted(ROOT.glob("ChatGPT Image*.png")) + sorted(ROOT.glob("ChatGPT Image*.jpg"))
    if matches:
        return matches[-1]
    raise SystemExit("No source icon found (assets/icons/theme-icon.png)")


def crop_content(im, pad_ratio: float = 0.04):
    """Trim empty margin. Keep pre-masked rounded-rect artwork as-is."""
    from PIL import Image, ImageChops

    rgba = im.convert("RGBA")
    # Transparent corners already mean a squircle / rounded-rect mask.
    if rgba.getpixel((0, 0))[3] < 8:
        return rgba
    bg = rgba.getpixel((0, 0))
    # Difference from corner color; keep pixels that aren't the outer canvas.
    bg_img = Image.new("RGBA", rgba.size, bg)
    diff = ImageChops.difference(rgba, bg_img).convert("L")
    bbox = diff.point(lambda p: 255 if p > 12 else 0).getbbox()
    if not bbox:
        return rgba
    left, top, right, bottom = bbox
    w, h = rgba.size
    pad = int(max(w, h) * pad_ratio)
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w, right + pad)
    bottom = min(h, bottom + pad)
    side = max(right - left, bottom - top)
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    left = max(0, cx - side // 2)
    top = max(0, cy - side // 2)
    right = min(w, left + side)
    bottom = min(h, top + side)
    return rgba.crop((left, top, right, bottom))


def to_square(im, size: int, bg=(0, 0, 0, 0)):
    from PIL import Image

    im = im.convert("RGBA")
    canvas = Image.new("RGBA", (size, size), bg)
    fitted = im.copy()
    fitted.thumbnail((size, size), Image.Resampling.LANCZOS)
    x = (size - fitted.width) // 2
    y = (size - fitted.height) // 2
    canvas.paste(fitted, (x, y), fitted)
    return canvas


def make_template(im, size: int):
    """Black-on-transparent glyph for macOS menu-bar template images."""
    from PIL import Image, ImageOps, ImageFilter

    rgba = im.convert("RGBA").resize((size * 4, size * 4), Image.Resampling.LANCZOS)
    gray = ImageOps.grayscale(rgba)
    # Darker strokes (headphones) become opaque black.
    mask = gray.point(lambda p: 255 if p < 210 else 0)
    alpha_src = rgba.split()[-1]
    mask = ImageChops_and(mask, alpha_src)
    mask = mask.filter(ImageFilter.MaxFilter(3))
    out = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    black = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    out.paste(black, mask=mask)
    return out.resize((size, size), Image.Resampling.LANCZOS)


def ImageChops_and(a, b):
    from PIL import ImageChops

    return ImageChops.multiply(a, b)


def write_icns(png_1024: Path, dest: Path) -> None:
    import shutil

    from PIL import Image

    iconset = dest.with_suffix(".iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    src = Image.open(png_1024).convert("RGBA")
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

    src = Image.open(png_1024).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    src.save(dest, format="ICO", sizes=sizes)


def main() -> None:
    from PIL import Image

    _require_pil()
    OUT.mkdir(parents=True, exist_ok=True)
    src_path = find_source()
    original = Image.open(src_path).convert("RGBA")
    if src_path.resolve() != SOURCE_STABLE.resolve():
        original.save(SOURCE_STABLE)
        print(f"[OK] copied source → {SOURCE_STABLE}")

    cropped = crop_content(original)
    app = to_square(cropped, 1024)
    app_path = OUT / "app.png"
    app.save(app_path)
    to_square(cropped, 128).save(OUT / "window.png")
    to_square(cropped, 44).save(OUT / "menubar.png")
    make_template(cropped, 22).save(OUT / "menubarTemplate.png")

    icns = ROOT / "packaging" / "EQCosplay.icns"
    ico = ROOT / "packaging" / "EQCosplay.ico"
    if sys.platform == "darwin":
        try:
            write_icns(app_path, icns)
        except Exception as exc:
            print(f"[WARN] icns: {exc}", file=sys.stderr)
    try:
        write_ico(app_path, ico)
    except Exception as exc:
        print(f"[WARN] ico: {exc}", file=sys.stderr)
    print(f"[OK] icons → {OUT}")


if __name__ == "__main__":
    main()
