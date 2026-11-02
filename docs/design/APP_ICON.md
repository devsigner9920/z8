# z8 launcher identity

2026-11-02: the user selected the folded command mark in
`brand/approved-logo.png` for the Android app icon. It joins the rounded prompt
and cursor into one negative-space stroke. The large upper-left/lower-right
corners and small opposite corners are part of the mark.

## Source and packaging

- `brand/approved-logo.png`: the selected ImageGen proof, including its label.
- `brand/z8-symbol-source.png`: built-in ImageGen transparency extraction. The
  surrounding canvas and `z8` label were removed; the folded path is transparent.
- `brand/z8-symbol.png`: cropped, neutral-black production raster with antialiasing.
- `brand/z8-app-icon.png`: 512px preview of the normal launcher presentation.
- `brand/launcher-preview.png`: generated mask/tint/size preview, not a screenshot
  of an installed app.
- `brand/icon-generation.json`: source hash, crop, tool version, dimensions and
  measured safe-zone radius.
- `brand/extraction-prompt.txt`: the final built-in ImageGen extraction prompt.

`tools/generate-app-icons.cjs` packages the real source raster without drawing or
approximating the logo's contours. It removes near-transparent noise, retains
edge antialiasing, and generates the checked-in resources. Regeneration requires
Node.js and sharp (generated with 0.35.5):

```sh
Z8_SHARP_MODULE=/absolute/path/to/installed/sharp node tools/generate-app-icons.cjs
```

Normal Android builds need neither Node.js nor ImageGen. They copy the checked-in
`overlay/` resources through `tools/prepare-app.py`.

## Android resources

The adaptive foreground is a transparent 432×432px bitmap, representing a 108dp
layer at 4× density. Its `BitmapDrawable` uses `gravity="fill"`, so it scales to
the runtime drawable bounds. The complete black mark is 46dp wide and sits
inside the 66dp-diameter safe circle (measured maximum radius about 32.17dp).
The white adaptive background keeps the selected silhouette visible rather than
merging its corners into a black launcher mask. The same transparent alpha is
used for Android's monochrome/themed icon.

This follows the layer and masking model described in
[Android's adaptive icon documentation](https://developer.android.com/develop/ui/compose/system/icon_design_adaptive).
The small inset preserves both near-square corners within the circular safe zone.

Both `mipmap-anydpi-v26/ic_launcher.xml` and `ic_launcher_round.xml` are overridden.
Normal and round legacy PNGs are generated at 48, 72, 96, 144 and 192px. The
manifest already references these names; no manifest or application-ID change
was needed. The foreground is also available to the themed icon API.

These are launcher identity assets. The generic Material terminal action icons,
in-app gradient badge, notifications and upstream checkout were not changed.

## Verification

The runtime APK build performs resource compilation, signing and alignment
validation plus the existing terminal-emulator tests. Icon-specific evidence is
stored in `reports/design/2026-11-02-app-icon/`. Native resource rendering there
loads the built APK with Android's framework without installing it over the
existing test app. This is resource/rendering validation, not a new full runtime
or Play-release qualification.
