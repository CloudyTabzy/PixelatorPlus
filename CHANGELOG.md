# Changelog

All notable changes to PixelatorPlus for Blender are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the extension version follows [Semantic Versioning](https://semver.org/)
(`blender_manifest.toml` is the single source of truth).

## [3.5.2] - 2026-09-28

### Fixed

- Render Sprite Sheet now stops immediately with a clear error when the scene
  has no render-enabled geometry, instead of rendering every frame in the
  scene range to blank images.

## [3.5.1] - 2026-09-28

### Fixed

- Tone Bands now rejects malformed or non-finite inputs clearly, falls back
  to image lightness where a Light Map is transparent, and handles many ID-map
  regions without repeatedly scanning the whole image for every part.
- Render ID Map and Render Light Map no longer overwrite unrelated images
  that happen to use the add-on's preferred output name; generated maps are
  safely refreshed for the scene that owns them.
- Sprite-sheet jobs use the layout and scale settings captured at startup,
  and cleanup restores scene settings and removes temporary frames after
  setup or render failures.
- Palette extraction controls now hide options that do not affect the selected
  method.
- Color Ramps accepts flat RGB samples and RGB/RGBA images, ignores
  transparent pixels, and rejects non-finite colors.
- The palette panel hides extraction controls that do not affect the selected
  method.

## [3.5.0] - 2026-09-28

### Added

- **Tone Bands** turns smooth shading into cel-style lightness bands. It can
  rank pixels by image lightness or a texture-free Workbench Light Map, and
  optionally gives each object or material its own bands using an ID Map.
  Sprite sheets render the required maps for every frame.
- **Color Ramps** extracts hue-family palettes with dark-to-light shades and
  pixel-art hue shifting. **Oklab (Hue First)** favors a pixel's color family
  over a closer lightness match when applying a palette.
- **Cel Sprite** style recipe, combining Tone Bands with Color Ramps.

### Fixed

- Shared sprite-sheet palettes now receive each frame's Light Map and ID Map
  while sampling Tone Bands, so map-driven sheets render consistently.

### Changed

- Plan schema version 6 adds the `shading` stage; older snapshots remain
  readable and keep their existing settings.

## [3.4.0] - 2026-09-28

### Added

- **Part Lines** in the Sprite section: one-pixel interior lines where two
  parts of the model meet, placed on the darker side so they read as shadow
  line work. They use the shared line color (Selective, Darkest, or Custom)
  and stay on the palette.
- **Render ID Map**: a flat, unantialiased Workbench render of the current
  frame with a distinct color per object or per material, pinned as the ID
  map that Part Lines read. Render Sprite Sheet renders one per frame
  automatically.

### Fixed

- With Auto Bake and Auto Connect on, every new render (and animation frame)
  was composited from the previous bake. The baked node is now detached for
  the duration of a render and reconnected with the fresh result.
- Sprite sheets render the 3D scene even when the video sequencer is active.

### Changed

- Plan snapshot keys are derived from the settings; outline color controls are
  labeled **Line Color** because they also drive Part Lines.

## [3.3.0] - 2026-09-28

### Added

- **Render Sprite Sheet**: renders the scene or a custom frame range, runs
  every frame through the exact pipeline, collapses frames to native pixel
  resolution (optional whole-number scale), and packs them into a sheet image.
  It runs one frame at a time with progress and Esc to cancel, keeps rendered
  frames in a temporary folder instead of memory, and restores every scene
  setting it touches.
- **Shared Palette**: one generated palette built from all frames, so
  animations never flicker.
- Sheet layouts (Grid, Row, Column), columns, spacing, padding, shared-box
  trimming, and empty-frame skipping, adapted from the Pixel Composer research.
- **Export Sprite Sheet**: PNG plus a TexturePacker/Aseprite-style JSON atlas
  with frame rectangles, durations, and the shared palette.

### Fixed

- Exporting with Blender Output Settings failed on Blender 5.x when the scene
  was set to video output, or for OpenEXR (which has no 8-bit depth). The
  exporter now selects the matching media type, falls back to the nearest
  supported depth and color mode, and reports every adjustment. Multilayer
  requests are saved as flat OpenEXR.

### Changed

- The pipeline accepts `images["shared_palette"]`, and
  `core.pipeline.build_shared_palette()` builds it from several frames.

## [3.2.0] - 2026-09-28

### Changed

- Redesigned sidebar. The essentials (input, recipe, Apply, and live
  preview) stay at the top; everything else lives in foldable **Pixels**,
  **Color**, **Dither**, **Sprite**, **Finish**, **Output**, **Advanced**,
  and (in the Compositor) **Compositor** sections. Folded sections show a
  summary such as `64 × 48 cells`, `Bayer`, or `Outline + Cleanup`;
  Posterize and Finish have header toggles. Labels use Blender's standard
  two-column layout.
- The separate **Advanced (V3)** sub-panels are gone. They repeated 43 main
  panel controls; their unique controls now live in the **Advanced** section.
- Controls that have no effect in the current mode are hidden (for example,
  blend mode and saturation in Palette Threshold dithering, or the match
  space for `.cube` LUTs).
- Plainer labels: *Generated Palette*, *Per Channel*, *Palette / LUT*,
  *Grayscale Dither*, *Palette Gamma*, *Sample Pixel Grid*, *Build Space* /
  *Match Space*, *Output Palette LUT*, *Output Identity LUT*, and *Capture /
  Restore Plan Snapshot*. Setting identifiers, saved files, and presets are
  unchanged.

### Fixed

- Generated palettes ignore fully transparent pixels, so a render's empty
  background no longer costs a palette entry or becomes the forced darkest
  color. Opaque images produce the same palettes as before.

## [3.1.0] - 2026-09-28

### Added

- **Sprite** stage (after Quantize, before Display Finish) for turning
  transparent renders into game sprites. **Remove Stray Pixels** replaces
  isolated cells with the color their neighbors agree on, and fills
  one-cell holes. **Outline** draws a one-cell Outside or Inside outline in
  Selective (darkened neighbor), Darkest palette, or Custom color, with
  optional corners. Both work on the pixel grid and stay palette-exact.
- **Freeze Palette for Animation**: applies once, saves the generated
  palette as an image, and switches quantization to it so every later frame
  maps onto identical colors.
- **Game Sprite** style recipe.
- The live preview reports when it is approximate (the 4K custom LUT is
  skipped) or out of date after an error, instead of silently keeping the
  previous image.

### Fixed

- `.cube` LUT paths relative to the saved `.blend` (`//...`, Blender's
  default) now load; the path property declares relative-path support on
  Blender versions that ask for it.
- Editing a `.cube` file in place now refreshes a cached live preview.
- Parsed LUTs are fingerprinted by content in the preview cache, and values
  that cannot be fingerprinted are rejected instead of keyed by identity.
- A stage stack saved by an older version can no longer place a newer stage
  out of dependency order.

### Changed

- Plan schema version 5 adds the `sprite` stage; schema 1–4 plans still load.
- Pipeline results include `source_palette_colors`, the palette before
  Palette Tint.

## [3.0.1] - 2026-09-28

### Fixed

- Apply outputs are owned per scene, source image, and output role, and are
  resized in place, so material and compositor references survive a change
  in output dimensions and scenes no longer overwrite each other's results.
- Palette Tint preserves each pixel's palette index, and the palette swatch,
  index image, and generated LUT describe the final tinted palette.
- Canonical plan stages and outputs take precedence over stale legacy flags;
  the default-LUT output has its own plan declaration.
- Plan snapshots keep values of disabled controls (explicit palette seed,
  Color Importance) so restoring a snapshot restores them.
- The Posterize alpha policy and the `.cube` LUT strength are honored in
  every path, including error diffusion.
- Live preview and Apply resolve the same custom image pins, so a custom
  Display Finish mask no longer fails in preview.
- Palette JSON is decoded by its declared format, so very dark RGB8 colors
  no longer load as white.
- The Advanced (V3) panel no longer creates or edits the stage stack while
  drawing, which Blender forbids. New scenes show an **Initialize Stage
  Stack** button; files with an incomplete stack show **Repair Stage Stack**.
  Pixelate is shown as a required, non-toggleable stage.
- Completing an intact stage stack no longer rewrites Pixelate's flag, so it
  no longer invalidates the live preview.
- Stage-stack repair keeps the dependency order when adding missing stages.
- Palette Threshold dithering now defaults to the RGB palette apply space
  like every other palette lookup (spec default for `Apply_Palette_Mode`).
- Dither-mask preview results now include the same `plan` key as normal
  results.
- Wire Output to Active Material is unavailable for objects that cannot hold
  materials (e.g. empties) instead of failing.
- Live preview no longer replaces the image in pinned Image Editors.

### Changed

- Trilinear `.cube` sampling works in bounded batches, and the parsed-LUT
  cache is a size-limited LRU.
- Faster nearest-palette lookup (about 2.8× on full-resolution palette
  snaps) and error diffusion (about 2.5–5× depending on the kernel). Both
  produce bit-identical output.
- Edge/flat dither masks and mask blur use a separable box filter, which
  avoids full-image index grids (roughly 1 GB peak on a 4K image) and is
  about 2× faster. Differences stay within 1.2e-7.
- Consolidated the quantize stage's repeated palette-snap and grid-diffusion
  branches into shared helpers; registration now uses
  `bpy.utils.register_classes_factory`.

### Removed

- The bundled 4096x4096 identity LUT image (`assets/luts/identity.png`,
  about 36 MB). **Output the Default LUT** generates the same image inside
  Blender, and the extension download shrinks by roughly 33 MB.
- The inspection-only `blue_noise_64.png` is no longer packaged; the add-on
  uses `blue_noise_64.npy` at runtime.

## [3.0.0] - 2026-08-18

### Added

- Promoted the staged pipeline to a canonical v3 executor with explicit
  dependency order, per-stage enable policy, schema version 4, and structured
  nested v3 settings.
- Added the **PixelatorPlus Creative Core**: **Index Guard** palette locking,
  **Palette Tint** index-preserving color styling, and **Grid Coherence** for
  dither-per-cell or final-cell output.
- Added a visible dependency-ordered V3 Stage Stack in the Advanced panel.

### Changed

- Made v3 plan policies and stage enable flags part of scene snapshots while
  retaining the flat v2 settings as an explicit migration/compatibility layer.
- Kept image pins as Blender datablock links and preserved the exact NumPy
  Apply/Export path; no external compositor runtime or copied Pixel Composer
  execution model was introduced.

### Compatibility

- Existing operator IDs, normal settings, presets, compositor bake workflow,
  and legacy plan snapshots remain readable. The v3 schema rejects invalid
  stage order instead of silently producing an ambiguous result.

## [2.8.0] - 2026-08-18

### Added

- Added a validated v3 plan snapshot format with stable fingerprints and JSON
  round-trip support.
- Added **Capture / Migrate** and **Restore** actions in the Advanced (V3)
  panel. Existing flat scene settings remain the compatibility surface; image
  datablock pins stay linked in Blender and are not copied into the snapshot.

### Changed

- Expanded plan normalization to retain advanced mask controls, custom dither
  resolution, and palette seed/weight settings during migration.
- Kept migration explicit and scene-local: the extension does not save user
  preferences or start background threads.

## [2.7.0] - 2026-08-18

### Added

- Added a real Posterize / Levels stage with full-range, image min/max, and
  robust percentile bounds, gamma-shaped thresholds, channel selection, mix,
  and alpha policy controls.
- Added named `strength_map`, `threshold_map`, and `range_map` image inputs to
  the shared staged pipeline contract.
- Added a bounded deterministic live-preview cache. It runs entirely on
  Blender's main thread; no Python worker threads are created.
- Added portable Palette JSON export and `.cube` LUT export from either the
  generated palette or a native 4K LUT, with compact 8³–64³ output sizes.
- Added stage cost metadata and regression coverage for the new contract,
  preview cache, Posterize stage, palette serialization, and LUT round trips.

### Changed

- The internal plan adapter now executes and gates the Posterize stage in the
  ordered pipeline while retaining the flat v2 settings and operator IDs.
- Preview applies named maps and caches identical capped-resolution results;
  Apply and Export continue to use the uncached NumPy reference path.
- Updated extension file-permission metadata for user-selected palette and LUT
  files while staying within Blender's manifest description limit.

## [2.6.3] - 2026-08-18

### Changed

- Restored Blender's native LUT enum popup so the two-column selector sizes to
  its contents instead of inheriting the full editor width.

## [2.6.2] - 2026-08-18

### Fixed

- Constrained the LUT selector popup to a compact fixed width so its two
  columns no longer expand across the surrounding Blender editor.

## [2.6.1] - 2026-08-18

### Changed

- Merged the identical TIC-80 and Sweetie-16 palette entries into one
  `TIC-80 / Sweetie 16` sidebar menu item while retaining both core palette
  identifiers for pipeline compatibility.

## [2.6.0] - 2026-08-18

### Added

- Added a collapsed **Advanced (V3)** nested panel to both the Image Editor and
  Compositor sidebars for the staged scaling, palette, portable LUT, and display
  finish controls.

### Changed

- Preserved the normal settings panel, Style Recipes, and **Surprise Me** as the
  primary workflow while exposing the same shared settings through the advanced
  panel; no duplicate settings state or migration is introduced.

## [2.5.0] - 2026-08-18

### Added

- Added an internal stage-plan compatibility layer while preserving the flat
  v2 settings and pipeline entry points.
- Added palette-aware threshold dithering with palette-boundary contrast and
  invert controls.
- Added frequency/exact-color palette extraction, palette sorting, shifting,
  trimming, replacement, and reusable pure-NumPy `PaletteAsset` utilities.
- Added Jarvis–Judice–Ninke and Linear error-diffusion kernels plus an explicit
  serpentine-scan toggle.
- Added portable `.cube` 3D-LUT import with domain-range handling,
  nearest/trilinear sampling, strength control, and parsed-file caching.
- Added Scale2x, Scale3x, CleanEdge-style, and capped content-aware scaling
  modes with content-aware seam selection.
- Added an optional display-finish stack: brightness, contrast, exposure,
  saturation, grain, scanlines, vignette, chromatic aberration, masks, and
  channel selection.
- Added pure-NumPy regression tests and Blender 5.2 E2E coverage for the new
  feature surface.

### Changed

- Extended the Blender permissions declaration to cover user-selected `.cube`
  LUT files.
- Kept the current compositor hybrid and v2 operator/settings compatibility
  boundary intact; the breaking nested-property migration remains reserved for
  a future 3.0 release.

## [2.4.0] - 2026-08-14

### Changed

- Replaced the subtle Gameboy Color and SNES 15-bit reducers with distinct,
  high-contrast 32-color presentation palettes. Every entry remains a valid
  RGB555 hardware color, while the compact palettes provide a clearly visible
  retro look.
- Added generated 4K image LUT presets for both stylized modes, including the
  previously missing SNES asset.

## [2.3.0] - 2026-08-14

### Added

- **Error Diffusion** for every quantization mode (Generate Custom Palette,
  Per Channel, Lookup Table / Palette): Floyd–Steinberg, Atkinson, and
  Sierra Lite kernels with a strength control. Diffusion snaps colors at
  pixel-grid resolution (area-downscale, serpentine diffusion, nearest
  upscale) for the classic Macintosh / newsprint look. Add-on extra.
- **New dither maps** (add-on extras): Halftone Dot (45-degree screen),
  Halftone Line, Crosshatch, Bayer 2x2 and 4x4, and Suzanne — an original
  hand-drawn Blender-monkey mascot threshold pattern in the spirit of the
  original filter's Amogus.
- **New dither mask sources** (add-on extras): Luminance Range and Saturation
  Range band masks with low/high sliders, Gradient Ramp mask with angle
  control, and Radial Falloff mask — plus Invert and Blur post-ops applicable
  to every mask type.
- **Expanded built-in palettes** (add-on extras; LUT list grew from 10 to 30
  entries): ZX Spectrum, Amstrad CPC, MSX, VIC-20, CGA/EGA, BBC Micro,
  SNES/Genesis/Apple IIGS bit-depth reducers, PICO-8, TIC-80, DawnBringer 32,
  Resurrect 64, Endesga 16/32, Sweetie 16, and 2/4/8/16-step grayscale ramps.
  Community palette values verified against their public sources; attributions
  recorded in `THIRD_PARTY_NOTICES.md`.
- **Three new style recipes**: Macintosh 1-Bit (Atkinson diffusion onto a
  2-step grayscale ramp), Newsprint Halftone (dot screen under a 4-step gray
  ramp), and Monkey Business (Suzanne dither over DawnBringer 32).
- `palette_from_image()` helper in `core/quantize.py` so the custom-palette
  image path and the diffusion path share one extraction implementation.

<!-- Earlier release history is documented retroactively by the maintainers. -->

## [2.2.1] - 2026-08-14

### Fixed

- Export dialogs now start with a sanitized basename derived from the relevant
  Blender image datablock: processed output, palette swatches, and 4K LUTs.
- Changing the selected processed-image format updates only the extension,
  preserving the descriptive image basename.

## [2.2.0] - 2026-08-14

### Added

- Expanded **Export Processed Image** beyond PNG and Targa to include JPEG,
  JPEG 2000, WebP, BMP, Targa Raw, TIFF, OpenEXR, OpenEXR MultiLayer, Radiance
  HDR, DPX, Cineon, and Iris, filtered against the host Blender build.
- A **Preserve Pixels** export path for writing the generated PixelatorPlus
  values directly.
- A **Blender Output Settings** path exposing color mode, bit depth, quality,
  compression, format codecs, preview embedding, and temporary scene color
  management.

### Changed

- Advanced exports restore every temporarily changed scene image setting after
  saving, including when an export raises an error.

## [2.1.0] - 2026-08-14

### Added

- Twelve editable style recipes covering modern indie, 1-bit ink, handheld,
  console, home-computer, demoscene, arcade, painterly, web-safe, and
  glitch-oriented looks.
- A bounded **Surprise Me** action that chooses a recipe and varies safe
  parameters such as resolution, dither strength, palette size, and seed.
- Deterministic recipe tests plus Blender E2E coverage for loading every recipe.

### Fixed

- The Compositor sidebar now initializes its settings reference before drawing
  the exact-output controls.

## [2.0.0] - 2026-08-14

### Added

- Added official-publication metadata, CloudyTabzy maintainer attribution,
  GPL-3.0-or-later source licensing, CC0 generated-asset licensing, and clean-
  room provenance notices.
- Added Blender extension validation and packaging hardening, including the
  final permissions declaration and exclusion of development artifacts from
  release archives.

### Changed

- Changed compositor asset registration from automatic preference mutation on
  enable to an explicit user action with repair behavior.
- Hardened packaging and documentation for Blender 5.2 forward compatibility.

## [1.4.1] - 2026-08-14

### Fixed

- Added Blender 5.2-compatible compositor handling through the modern
  `Scene.compositing_node_group` and `NodeGroupOutput` boundary while retaining
  compatibility with the 5.0 compositor tree.
- Updated the extension build helper to discover Blender 5.2, 5.1, and 5.0
  installations.

## [1.4.0] - 2026-08-14

### Changed

- Unified the previously version-gated control surface into one non-versioned
  panel so dithering, masks, Oklab, custom palette inputs, fixed-size dither
  variants, and other reconstructed controls are available together.
- Removed the redundant filter-version selector and updated parameter
  collection to carry the complete settings surface.

## [1.3.0] - 2026-08-14

### Added

- Added the hybrid exact compositor workflow: bake the full NumPy result into
  a named compositor Image node from either the input image or Render Result.
- Added explicit connection of the baked output to the compositor output and
  optional auto-baking after completed renders, with auto-connect kept as a
  separate opt-in.

## [1.2.0] - 2026-08-14

### Added

- Added native Blender compositor node-group assets for adjustable Pixelate,
  fixed 4px/8px/16px Pixelate variants, and Pixelate + Posterize recipes.
- Added the bundled compositor asset catalog and generator tooling, with asset
  metadata and CC0 declarations.

## [1.1.0] - 2026-08-14

### Added

- Evolved the native Blender workflow with debounced capped live preview,
  Draft versus Final preview modes, palette and palette-index outputs, and
  safer generated-image handling.
- Added native material hookup from the processed image to Principled BSDF Base
  Color with Closest interpolation, plus the Base Color grab workflow.
- Improved quantization controls, explicit seeds, output handling, and
  color-management-safe image export behavior.

## [1.0.0] - 2026-08-14

### Added

- Initial native Blender 4.2+ extension implementation of the reconstructed
  PixelatorPlus v2.72 workflow.
- Pure NumPy color-space, pixelation, dithering, quantization, palette, and 4K
  LUT pipeline behind a thin optional-`bpy` boundary.
- Nearest and Nearest Softer pixelation, white/blue-noise and ordered/custom
  dither maps, edge/flat/custom masks, RGB/CIELAB/Oklab palette generation,
  per-channel reduction, vintage built-in palettes, custom LUTs, and PNG/Targa
  output operators.
- Headless-Blender E2E coverage, deterministic core tests, blue-noise assets,
  and extension packaging tools.
