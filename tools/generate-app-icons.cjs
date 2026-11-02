#!/usr/bin/env node
// Package the approved raster mark; this script does not draw logo geometry.
// Generated with sharp 0.35.5 (or set Z8_SHARP_MODULE to an installed sharp module).
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const sharp = require(process.env.Z8_SHARP_MODULE || 'sharp');

const root = path.resolve(__dirname, '..');
const brand = path.join(root, 'docs/design/brand');
const res = path.join(root, 'overlay/app/src/main/res');
const source = path.join(brand, 'z8-symbol-source.png');
const viewport = 108;
const visibleViewport = 72;
const markWidth = 46;
const densities = {mdpi: 48, hdpi: 72, xhdpi: 96, xxhdpi: 144, xxxhdpi: 192};
const transparent = {r: 0, g: 0, b: 0, alpha: 0};

async function write(file, data) {
  await fs.mkdir(path.dirname(file), {recursive: true});
  await fs.writeFile(file, data);
}

async function mask(size, round) {
  const shape = round
    ? `<circle cx="${size / 2}" cy="${size / 2}" r="${size / 2}" fill="white"/>`
    : `<rect width="${size}" height="${size}" rx="${size * 0.22}" fill="white"/>`;
  return Buffer.from(`<svg width="${size}" height="${size}">${shape}</svg>`);
}

async function main() {
  const {data, info} = await sharp(source).ensureAlpha().raw().toBuffer({resolveWithObject: true});
  let left = info.width, top = info.height, right = -1, bottom = -1;
  for (let y = 0; y < info.height; y++) {
    for (let x = 0; x < info.width; x++) {
      const i = (y * info.width + x) * 4;
      // Remove near-transparent generation noise while retaining antialiasing.
      data[i] = data[i + 1] = data[i + 2] = 0;
      data[i + 3] = data[i + 3] < 8 ? 0 : data[i + 3] > 247 ? 255 : data[i + 3];
      if (data[i + 3] > 127) {
        left = Math.min(left, x); top = Math.min(top, y);
        right = Math.max(right, x); bottom = Math.max(bottom, y);
      }
    }
  }
  if (right < left || bottom < top) throw new Error('The source has no opaque mark.');
  const crop = {left: Math.max(0, left - 2), top: Math.max(0, top - 2),
    width: Math.min(info.width - Math.max(0, left - 2), right - left + 5),
    height: Math.min(info.height - Math.max(0, top - 2), bottom - top + 5)};
  const mark = await sharp(data, {raw: info}).extract(crop).png().toBuffer();
  await write(path.join(brand, 'z8-symbol.png'), mark);

  const layerSize = viewport * 4;
  const scaled = await sharp(mark).resize(markWidth * 4, markWidth * 4,
    {fit: 'contain', background: transparent}).png().toBuffer();
  const foreground = await sharp({create: {width: layerSize, height: layerSize,
    channels: 4, background: transparent}}).composite([{input: scaled, gravity: 'centre'}]).png().toBuffer();
  await write(path.join(res, 'drawable-nodpi/z8_launcher_foreground.png'), foreground);

  // Both sharp outer corners fit within the 66dp-diameter adaptive safe circle.
  const raw = await sharp(foreground).raw().toBuffer();
  let maxRadius = 0;
  for (let y = 0; y < layerSize; y++) for (let x = 0; x < layerSize; x++) {
    if (raw[(y * layerSize + x) * 4 + 3] > 16)
      maxRadius = Math.max(maxRadius, Math.hypot(x + 0.5 - layerSize / 2, y + 0.5 - layerSize / 2) / 4);
  }
  if (maxRadius > 33) throw new Error('Launcher artwork exceeds the adaptive safe circle.');

  async function icon(size, round, background = '#ffffff', tint = null) {
    let glyph = await sharp(mark).resize(Math.round(size * markWidth / visibleViewport),
      Math.round(size * markWidth / visibleViewport), {fit: 'contain', background: transparent}).png().toBuffer();
    if (tint) {
      const meta = await sharp(glyph).metadata();
      glyph = await sharp({create: {width: meta.width, height: meta.height, channels: 4, background: tint}})
        .composite([{input: glyph, blend: 'dest-in'}]).png().toBuffer();
    }
    const square = await sharp({create: {width: size, height: size, channels: 4, background}})
      .composite([{input: glyph, gravity: 'centre'}]).png().toBuffer();
    return sharp(square).composite([{input: await mask(size, round), blend: 'dest-in'}]).png().toBuffer();
  }
  for (const [density, size] of Object.entries(densities)) {
    await write(path.join(res, `mipmap-${density}/ic_launcher.png`), await icon(size, false));
    await write(path.join(res, `mipmap-${density}/ic_launcher_round.png`), await icon(size, true));
  }
  await write(path.join(brand, 'z8-app-icon.png'), await icon(512, false));

  const report = {source: 'docs/design/brand/z8-symbol-source.png', sharpVersion: sharp.versions.sharp,
    sourceSha256: crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex'),
    crop, adaptiveViewportDp: viewport, visibleViewportDp: visibleViewport,
    symbolWidthDp: markWidth, safeCircleRadiusDp: 33, actualRadiusDp: maxRadius,
    foregroundPixels: layerSize, legacyDensities: densities,
    background: '#ffffff', monochrome: 'Same transparent foreground alpha; launcher supplies tint'};
  await write(path.join(brand, 'icon-generation.json'), JSON.stringify(report, null, 2) + '\n');

  const samples = [await icon(192, true), await icon(192, false),
    await icon(192, true, '#dbe3ff', '#283961'), await icon(192, false, '#283345', '#dbe3ff')];
  const labels = ['Round', 'Rounded square', 'Themed light', 'Themed dark'];
  const images = samples.map((png, i) => `<image x="${70 + i * 285}" y="95" width="192" height="192" href="data:image/png;base64,${png.toString('base64')}"/><text x="${166 + i * 285}" y="329" text-anchor="middle">${labels[i]}</text>`).join('');
  const small = [];
  for (const [i, size] of [24, 32, 48, 64, 96].entries()) {
    const png = await icon(size, false);
    small.push(`<image x="${115 + i * 220}" y="${470 - size / 2}" width="${size}" height="${size}" href="data:image/png;base64,${png.toString('base64')}"/><text x="${115 + i * 220 + size / 2}" y="550" text-anchor="middle">${size}px</text>`);
  }
  const board = `<svg width="1200" height="600" xmlns="http://www.w3.org/2000/svg"><rect width="1200" height="600" fill="#f0f2f6"/><g font-family="Arial,sans-serif" font-size="18" fill="#273041"><text x="60" y="50" font-size="24">z8 / Launcher icon</text>${images}<path d="M60 370H1140" stroke="#d9dfe8"/><text x="60" y="410">Actual pixel sizes</text>${small.join('')}</g></svg>`;
  await write(path.join(brand, 'launcher-preview.png'), await sharp(Buffer.from(board)).png().toBuffer());
  console.log(JSON.stringify(report, null, 2));
}

main().catch(error => {console.error(error); process.exitCode = 1;});
