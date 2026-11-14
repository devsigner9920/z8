# Store graphics

`render.py` uses the existing approved Z8 icon and Prism artwork. It performs
only layout and mechanical packaging; it does not generate or reconstruct the
logo and does not invent app screenshots.

Run from any directory with Python 3 and Pillow:

```sh
python3 docs/store/graphics/render.py
```

The default output is `artifacts/play-store/2026-11-14/graphics/`:

- `z8-store-icon.png`: 512 × 512, 32-bit RGBA PNG, sRGB, at most 1 MB.
- `z8-feature-graphic-en-US.png`: 1,024 × 500, RGB PNG, sRGB.
- `z8-feature-graphic-en-US.svg`: self-contained editable layout counterpart.
- `graphics-manifest.json`: dimensions, formats, hashes, inputs and alt text.

The existing `z8-app-icon.png` is a launcher preview with transparent rounded
corners. The store export fills only that outer transparency white and leaves
the approved mark and its placement unchanged. Google applies its own mask;
see [the Play icon specifications](https://developer.android.com/distribute/google-play/resources/icon-design-specifications).

The feature graphic crops the existing Prism artwork to landscape, overlays a
navy fade and decorative lines, and adds English text. It contains no terminal
output or mock app interface. The small brand icon is proportionally resized.

Default text rendering uses installed Arial on macOS or DejaVu Sans on Linux;
pass `--font-regular` and `--font-bold` for explicit font files. Font files are
not redistributed. The manifest records their names and hashes. Different fonts
can change output, so review newly rendered images before upload. The PNG is
the upload artifact; SVG text can vary with the editor's installed fonts.

The maintainer confirmed GPL-3.0-only redistribution rights for the logo and
Prism image on 2026-11-02. Original source files and their notices are preserved.
