# PixelatorPlus for Blender

**Turn any image, texture, or render into crisp retro pixel art without leaving
Blender.**

![Blender 4.2+](https://img.shields.io/badge/Blender-4.2%2B-orange?logo=blender&logoColor=white)
![Tested on Blender 5.2 LTS](https://img.shields.io/badge/tested-Blender%205.2%20LTS-blue)
![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-green)

PixelatorPlus is a native Blender extension for pixelation, dithering, and
color quantization. Pick an image, choose a look, and press **Apply**. You get
pixel-perfect sprites, hand-made-looking textures, and authentic console
palettes in seconds. Everything runs inside Blender with no Substance plug-in,
external app, or internet connection required.

## Why PixelatorPlus?

- **Instant retro looks.** Sixteen one-click **Style Recipes**, from *1-Bit
  Ink* and *Handheld 4-Tone* to *Demoscene 32*, *Newsprint Halftone*, and
  *Game Sprite*. Every recipe stays fully editable.
- **Feeling stuck? Press Surprise Me.** It picks a recipe and tastefully
  varies the resolution, dither, palette, and seed. It's a quick way to find a
  look you wouldn't have dialed in yourself.
- **Real hardware palettes.** NES, Game Boy and Game Boy Color, C64, Amiga,
  Apple II, Atari 2600, Master System, ZX Spectrum, CGA/EGA, MSX, PICO-8,
  DawnBringer 32, Resurrect 64, Endesga, and more. You can also generate a
  palette from your own image.
- **From 3D render to game sprite.** Render your model with a transparent
  background, then let PixelatorPlus clean up stray pixels and draw a crisp
  one-pixel outline, just like a pixel artist would.
- **Line work only Blender can see.** **Part Lines** read your scene to find
  where a model's parts meet (arm against torso, head against body) and draw
  the interior pixel lines an artist would add by hand.
- **Animation to sprite sheet in one click.** **Render Sprite Sheet** renders
  your animation, pixelates every frame with one shared palette (no color
  flicker), and packs them into a game-ready sheet with a JSON atlas.
- **Pixel art that stays pixel art.** Unique **Palette Lock** and **Grid
  Coherence** controls keep finishing effects from smearing your palette or
  breaking the pixel grid.
- **Works where you work.** Available in both the **Image Editor** and the
  **Compositor** sidebars, with one click to wire the result into your
  material.
- **Fast feedback.** A live preview updates while you tweak, and the
  full-resolution result appears when you Apply.

## Features

### Pixelate

- Square or separate X/Y pixel counts, up to 2048 cells per axis.
- **Nearest** for hard blocks or **Nearest Softer** for averaged block colors.
- Pixel-art upscalers: **Scale2x**, **Scale3x**, a **CleanEdge**-style
  smoother, and content-aware grid scaling.
- Viewport-only **Bilinear** and **N64 3-Point** preview filtering, for
  checking how the art reads on classic hardware. It is never baked into your
  output.

### Dither

- **Bayer** 2×2, 4×4, and 8×8, **Blue Noise**, **White Noise**, clustered
  **Pattern**, **Halftone Dot/Line**, **Crosshatch**, and the playful
  **Amogus** and **Suzanne** patterns. You can also bring your own dither
  texture.
- **Palette Threshold** mode dithers between the two nearest palette colors
  for clean, ordered ramps that never leave your palette.
- Smart masks aim the dither where you want it: edges or flat areas (with
  seven frequency bands), luminance or saturation bands, gradients, radial
  falloff, or your own mask image.
- **Lock Dither to Pixel Grid** gives exactly one dither decision per pixel.

### Color

- **Generate Custom Palette** extracts 2–256 colors with k-means (in RGB,
  CIELAB, or Oklab), frequency, or exact-color extraction. Palettes can be
  sorted, shifted, trimmed, or swapped against another palette.
- **Freeze Palette for Animation** saves the generated palette as an image
  and switches to it, so later frames and renders never drift.
- **Built-in palettes and reducers** cover dozens of classic machines and
  fantasy consoles, plus grayscale ramps.
- **Error diffusion** with Floyd–Steinberg, Atkinson, Sierra Lite,
  Jarvis–Judice–Ninke, or Linear, and serpentine scanning, for the classic
  Macintosh and newsprint look.
- **Posterize / Levels** gives restrained color steps with robust ranges,
  gamma, and per-channel control.
- **LUTs everywhere**: use standard `.cube` 3D LUTs or 4K image LUTs, and
  export your palette as a `.cube` or 4K LUT for use in other apps.

### Sprite

- **Remove Stray Pixels** replaces isolated specks with the color their
  neighbors agree on. It also fills one-pixel holes, while one-pixel-wide
  lines stay intact.
- **Outline** draws a one-pixel border **Outside** the silhouette or along
  its **Inside** edge. Choose a **Selective** outline (a darker shade of the
  neighboring color, the classic pixel-art "sel-out"), the **Darkest** palette
  color, or a **Custom** color. Outlines stay on your palette.
- **Outline Corners** adds diagonal pixels for a heavier, rounder look.
- **Part Lines** draw one-pixel lines where two parts of your model meet,
  always on the shadow side. Parts are your **Objects** or **Materials**.
  **Render ID Map** captures them for a single image, and **Render Sprite
  Sheet** does it for every frame automatically.

### Sprite Sheet

- **Render Sprite Sheet** renders the scene or a custom frame range (with a
  frame step), pixelates each frame, and packs them into one image. Press
  **Esc** to cancel; your render settings are always restored.
- Frames are saved at **native resolution**, one sprite pixel per image
  pixel, with an optional whole-number **Pixel Scale**.
- **Grid**, **Row**, or **Column** layouts, with columns, spacing, and
  padding. **Trim Empty Space** crops every frame to the same box, so the
  animation stays aligned; **Skip Empty Frames** drops blank ones.
- **Shared Palette** builds one palette from all frames at once.
- **Export Sprite Sheet** writes the PNG plus a TexturePacker/Aseprite-style
  JSON atlas (frame rectangles, durations, and the palette) that Godot,
  Phaser, PixiJS, and most engines can import.

### Finish

- Brightness, contrast, exposure, saturation, film grain, CRT scanlines,
  vignette, and chromatic aberration. All of them can be masked and applied
  per channel.
- **Palette Lock**: *Index Guard* snaps finished pixels back to your palette,
  and *Palette Tint* restyles the palette colors themselves while every pixel
  keeps its palette slot.
- **Grid Coherence** collapses the finished image back onto the pixel grid.

### Output

- Export to PNG, JPEG, JPEG 2000, WebP, BMP, Targa, TIFF, OpenEXR, Radiance
  HDR, DPX, Cineon, or Iris. **Preserve Pixels** writes exact values, while
  Blender's output settings give you full control over bit depth, codecs, and
  color management.
- Export a palette swatch, a palette-index image, a 4K LUT, a `.cube` LUT, or
  a portable palette JSON file.
- **Wire Output to Active Material** plugs the result into Base Color with
  crisp *Closest* texture filtering, ready for your game-art viewport.

## Compositor Integration

**Drag-and-drop node presets.** Add the bundled library once from the
Compositor sidebar. Native *Pixelate* and *Pixelate + Posterize* node groups
then appear in the Asset Shelf, ready to drop into any compositor tree and
fully editable.

**Exact, full-quality output.** Bake the complete PixelatorPlus result,
including dithers, palettes, masks, and LUTs, into a compositor Image node
from your input image or your latest render. You can optionally re-bake
automatically after every render.

## Install

1. Download the latest `pixelatorplus-<version>.zip` from the
   [Releases](../../releases) page.
2. In Blender, open **Edit → Preferences → Get Extensions**, then use the
   drop-down menu to choose **Install from Disk…** and pick the ZIP.
3. Enable **PixelatorPlus**.

Requires **Blender 4.2 or newer**. Tested on Blender 5.2 LTS.

## Quick Start

1. Open the **Image Editor** or **Compositor**, press **N**, and select the
   **PixelatorPlus** tab.
2. Choose an **Input** image. The material button next to it grabs the active
   object's Base Color texture.
3. Load a **Style Recipe**, or press **Surprise Me**.
4. Turn on **Live Preview** and tweak the settings until it feels right.
5. Press **Apply PixelatorPlus**. Your result appears as
   `<image name> [PixelatorPlus]`, and repeat runs update that same image.

Making sprites? Load the **Game Sprite** recipe, point a camera at your
animated model, and press **Render Sprite Sheet**. The background is rendered
transparent automatically, so outlines follow the silhouette.

The sidebar keeps the essentials (input, recipe, Apply, live preview) at
the top. Below them, foldable **Pixels**, **Color**, **Dither**, **Sprite**,
**Finish**, and **Output** sections show a one-line summary while folded, so
you can see the whole setup at a glance. **Advanced** holds Palette Lock,
Grid Coherence, the stage stack, and restorable plan snapshots.

## Credits and License

PixelatorPlus began as a clean-room reimagining of the workflow of the classic
**Pixel8r** Substance filter, then grew well beyond it. It contains no Pixel8r
code, binaries, or assets, and it is not affiliated with or endorsed by
Pixel8r's rights holders. Built-in palettes are rebuilt from public
definitions and credited in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Copyright (C) 2026 CloudyTabzy.

- Program source: **GPL-3.0-or-later** (see [LICENSE](LICENSE)).
- Bundled textures, LUTs, palettes, and compositor assets: **CC0-1.0** (see
  [assets/ASSET_LICENSE.txt](assets/ASSET_LICENSE.txt)).

See [CHANGELOG.md](CHANGELOG.md) for release history.
