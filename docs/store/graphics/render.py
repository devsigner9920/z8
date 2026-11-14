#!/usr/bin/env python3
"""Package existing Z8 artwork and render the English Play feature graphic.

Requires Pillow. No network access, generated UI or logo tracing is involved.
The approved logo's contours and its existing 512px icon placement are retained.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[3]
ICON = ROOT / "docs/design/brand/z8-app-icon.png"
PRISM = ROOT / "overlay/app/src/main/assets/z8/design/prism-reference.png"
SIZE = (1024, 500)
SCALE = 3
NAVY = (12, 18, 33)
TEXT = [
    (136, 79, "Z8", 28, "bold", "#f7f8ff"),
    (80, 174, "Development", 60, "bold", "#f7f8ff"),
    (80, 242, "terminal", 60, "bold", "#f7f8ff"),
    (82, 338, "Linux tools. On your Android.", 25, "regular", "#d4d9ea"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font_path(supplied: str | None, bold: bool) -> Path:
    if supplied:
        result = Path(supplied).expanduser()
        if not result.is_file():
            raise SystemExit(f"Font does not exist: {result}")
        return result
    choices = (
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
             "/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in choices:
        if candidate.is_file():
            return candidate
    raise SystemExit("Provide --font-regular and --font-bold font file paths.")


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "artifacts/play-store/2026-11-14/graphics")
    parser.add_argument("--font-regular")
    parser.add_argument("--font-bold")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fonts = {
        "regular": font_path(args.font_regular, False),
        "bold": font_path(args.font_bold, True),
    }
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()

    # A launcher preview has pre-rounded transparent corners. Play applies its
    # own mask, so only fill those corners white; do not change any logo pixels.
    original = Image.open(ICON).convert("RGBA")
    if original.size != (512, 512):
        raise SystemExit("Expected the approved 512px icon; do not rescale silently.")
    icon = Image.new("RGBA", original.size, "white")
    icon.alpha_composite(original)
    icon_file = output / "z8-store-icon.png"
    icon.save(icon_file, icc_profile=srgb, optimize=True)

    # Crop the existing Prism image to the banner aspect ratio. A navy fade
    # gives the copy a quiet surface while retaining the real brand colors.
    working_size = tuple(value * SCALE for value in SIZE)
    graphic = ImageOps.fit(Image.open(PRISM).convert("RGB"), working_size,
                           Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    fade = Image.new("L", (SIZE[0], 1))
    fade.putdata([round(255 * (0.98 if x < 520 else
                              0.98 - 0.90 * min(1, (x - 520) / 504)))
                  for x in range(SIZE[0])])
    fade = fade.resize(working_size, Image.Resampling.BICUBIC)
    graphic = Image.composite(Image.new("RGB", working_size, NAVY), graphic, fade)
    draw = ImageDraw.Draw(graphic)
    # Decorative lines, not a representation of app chrome or terminal output.
    for x, color in ((705, "#ffffff"), (833, "#c1c9f3"), (961, "#ffffff")):
        layer = Image.new("RGBA", working_size)
        ld = ImageDraw.Draw(layer)
        rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        ld.line(((x * SCALE, -40 * SCALE),
                 ((x - 260) * SCALE, 540 * SCALE)), fill=(*rgb, 26), width=2)
        graphic = Image.alpha_composite(graphic.convert("RGBA"), layer).convert("RGB")
    graphic.paste(original.resize((40 * SCALE, 40 * SCALE), Image.Resampling.LANCZOS),
                  (80 * SCALE, 75 * SCALE),
                  original.resize((40 * SCALE, 40 * SCALE), Image.Resampling.LANCZOS))
    draw = ImageDraw.Draw(graphic)
    for x, y, text, size, weight, color in TEXT:
        font = ImageFont.truetype(str(fonts[weight]), size * SCALE)
        box = draw.textbbox((x * SCALE, y * SCALE), text, font=font, anchor="lt")
        if box[2] > 650 * SCALE or box[3] > 445 * SCALE:
            raise SystemExit(f"Text exceeds the intended safe area: {text}")
        draw.text((x * SCALE, y * SCALE), text, font=font, fill=color, anchor="lt")
    graphic = graphic.resize(SIZE, Image.Resampling.LANCZOS)
    graphic_file = output / "z8-feature-graphic-en-US.png"
    graphic.save(graphic_file, icc_profile=srgb, optimize=True)

    # Editable, self-contained SVG alternative; the PNG above is the verified
    # upload artifact. SVG font substitution can change line widths on hosts.
    texts = "\n".join(
        f'<text x="{x}" y="{y}" dominant-baseline="hanging" font-size="{size}" '
        f'font-weight="{700 if weight == "bold" else 400}" fill="{color}">{escape(text)}</text>'
        for x, y, text, size, weight, color in TEXT
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="500" viewBox="0 0 1024 500">
<title>Z8 development terminal</title>
<desc>Linux tools. On your Android. Existing Z8 logo and Prism artwork with a dark background.</desc>
<defs><linearGradient id="fade"><stop offset="0" stop-color="#0c1221" stop-opacity=".98"/><stop offset=".5078" stop-color="#0c1221" stop-opacity=".98"/><stop offset="1" stop-color="#0c1221" stop-opacity=".08"/></linearGradient></defs>
<image width="1024" height="500" preserveAspectRatio="xMidYMid slice" href="{data_uri(PRISM)}"/>
<rect width="1024" height="500" fill="url(#fade)"/>
<g stroke="#ffffff" stroke-opacity=".1" stroke-width=".667"><path d="M705 -40L445 540"/><path d="M833 -40L573 540"/><path d="M961 -40L701 540"/></g>
<image x="80" y="75" width="40" height="40" href="{data_uri(ICON)}"/>
<g font-family="Arial, sans-serif">{texts}</g>
</svg>
'''
    (output / "z8-feature-graphic-en-US.svg").write_text(svg, encoding="utf-8")

    records = []
    for path in (icon_file, graphic_file):
        with Image.open(path) as im:
            record = {"file": path.name, "width": im.width, "height": im.height,
                      "mode": im.mode, "bytes": path.stat().st_size,
                      "sha256": sha(path), "iccProfile": "sRGB"}
            records.append(record)
    assert records[0]["mode"] == "RGBA" and records[0]["bytes"] <= 1024 * 1024
    assert records[1]["mode"] == "RGB"
    manifest = {
        "schemaVersion": 1,
        "kind": "store-graphics-not-app-screenshots",
        "preparedDate": "2026-11-14",
        "sources": [{"file": str(p.relative_to(ROOT)), "sha256": sha(p)}
                    for p in (ICON, PRISM)],
        "logoTreatment": "Unchanged logo contours and placement; icon's outer transparent corners filled white for Play masking. Feature icon only proportionally resized.",
        "featureTreatment": "Existing Prism artwork cropped to landscape, navy fade, decorative lines and text; no fabricated app UI.",
        "fontFiles": {weight: {"filename": path.name, "sha256": sha(path)}
                      for weight, path in fonts.items()},
        "fontFilesRedistributed": False,
        "files": records,
        "altText": {
            icon_file.name: "Z8's black folded terminal mark on a white background.",
            graphic_file.name: "Z8 development terminal. Linux tools on Android, with a dark background and Prism colors."
        },
        "visualReview": "pending",
    }
    (output / "graphics-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
