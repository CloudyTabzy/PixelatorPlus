"""Enum item lists for PixelatorPlus settings.

Identifiers are the snake_case keys that flow into ``collect_params()`` and
``run_pipeline()``; their order and v2.72 labels follow the reverse-engineering
spec.  Plain data: no Blender import needed.
"""


DITHER_TYPES = [
    ("NONE", "None", "No dithering"),
    ("WHITE_NOISE", "White Noise", "Seeded white-noise threshold map"),
    ("BLUE_NOISE", "Blue Noise", "Tileable blue-noise threshold map"),
    ("BAYER", "Bayer", "8x8 ordered Bayer matrix"),
    ("PATTERN", "Pattern", "Built-in 8x8 clustered-dot pattern"),
    ("CUSTOM", "Custom Dither Pattern", "Custom dither texture (any square resolution)"),
    ("CUSTOM_8X8", "Custom Dither 8x8 px", "Custom dither texture fixed at 8x8 pixels"),
    ("CUSTOM_16X16", "Custom Dither 16x16 px", "Custom dither texture fixed at 16x16 pixels"),
    ("AMOGUS", "Amogus", "Crewmate threshold pattern"),
    # add-on extras (not from the Substance spec)
    ("BAYER_2X2", "Bayer 2x2", "2x2 ordered Bayer matrix"),
    ("BAYER_4X4", "Bayer 4x4", "4x4 ordered Bayer matrix"),
    ("HALFTONE_DOT", "Halftone Dot", "45-degree halftone dot screen"),
    ("HALFTONE_LINE", "Halftone Line", "Diagonal halftone line screen"),
    ("CROSSHATCH", "Crosshatch", "Two perpendicular halftone line screens"),
    ("SUZANNE", "Suzanne", "Blender monkey threshold pattern — our own mascot dither"),
]


BLEND_MODES = [
    ("OVERLAY", "Overlay", "Overlay blend in sRGB space"),
    ("OVERLAY_LINEAR", "Overlay (Linear)", "Overlay blend in linear light"),
    ("SOFT_LIGHT", "Soft Light", "Soft-light blend in sRGB space"),
    ("SOFT_LIGHT_LINEAR", "Soft Light (Linear)", "Soft-light blend in linear light"),
]


DITHER_STRATEGIES = [
    ("OVERLAY", "Texture Overlay", "Blend the threshold map into the image before quantization"),
    ("PALETTE_THRESHOLD", "Palette Threshold", "Choose between the two nearest palette colors using the threshold map"),
]


SCALE_ALGORITHMS = [
    ("NEAREST", "Nearest", "Keep ordinary nearest-neighbor pixel blocks"),
    ("SCALE2X", "Scale2x", "Edge-aware 2x pixel-art scaling"),
    ("SCALE3X", "Scale3x", "Edge-aware 3x pixel-art scaling"),
    ("CLEANEDGE", "CleanEdge", "Tolerance-aware CleanEdge-style 2x scaling"),
    ("CONTENT_AWARE", "Content Aware", "Capped seam-carving reconstruction for small grids"),
]


MASK_TYPES = [
    ("NONE", "None", "Dither everywhere (v2.72 default)"),
    ("EDGES", "Dither by Edges", "Dither only detailed/edge areas"),
    ("FLATS", "Dither by Flats", "Dither only flat areas"),
    ("CUSTOM", "Custom Dither Mask Texture", "Use a custom mask image"),
    # add-on extras (not from the Substance spec)
    ("LUMINANCE", "Luminance Range", "Dither only a luminance band"),
    ("SATURATION", "Saturation Range", "Dither only a saturation band"),
    ("GRADIENT", "Gradient Ramp", "Positional ramp mask at a configurable angle"),
    ("RADIAL", "Radial Falloff", "Dither falls off from the image center"),
]


# v2.72 relabels the LUT quantize mode "Lookup Table / Palette"
QUANTIZE_TYPES = [
    ("NONE", "None", "No color quantization"),
    ("CUSTOM_PALETTE", "Generated Palette",
     "Extract a palette from the image in the chosen color space (slower)"),
    ("PER_CHANNEL", "Per Channel",
     "Reduce each channel to N colors / bits"),
    ("LUT", "Palette / LUT",
     "Snap to a built-in vintage palette, a custom 4K LUT, or a custom palette image"),
]


INIT_MODES = [
    ("1", "Mode 1", "Random pixel initialization"),
    ("2", "Mode 2", "K-means++ initialization"),
    ("3", "Mode 3", "Luminance-spaced initialization"),
    ("4", "Mode 4", "Unique-color initialization"),
]


COLOR_MODES = [
    ("RGB", "RGB", "Cluster in RGB"),
    ("CIELAB", "CIELAB", "Cluster in CIELAB (perceptual)"),
    ("OKLAB", "Oklab", "Cluster in Oklab (perceptual)"),
]


APPLY_MODES = [
    ("RGB", "RGB", "Match palette colors in RGB"),
    ("CIELAB", "CIELAB", "Match palette colors in CIELAB"),
    ("OKLAB", "Oklab", "Match palette colors in Oklab"),
    # -- add-on extra (not from the Substance spec)
    ("OKLAB_HUE", "Oklab (Hue First)",
     "Match in Oklab, preferring a shade of the right color over the exact lightness "
     "(keeps pixels in their color ramp)"),
]


FORCE_COLORS = [
    ("NONE", "None", "No forced colors"),
    ("DARKEST_BRIGHTEST", "Darkest Brightest",
     "Replace two least-used K-means colors with the image's darkest and brightest colors"),
    ("BLACK_WHITE", "Black White",
     "Replace two least-used K-means colors with pure black and pure white"),
]


LUTS = [
    ("CUSTOM_LUT", "Custom LUT", "User-supplied 4096x4096 LUT image"),
    ("CUBE_LUT", ".cube 3D LUT", "User-selected portable .cube 3D LUT file"),
    ("CUSTOM_PALETTE", "Custom Palette", "User-supplied palette image"),
    ("AMIGA", "Amiga", "Deluxe Paint 4 (Amiga) 32 colors"),
    ("APPLE2_LORES", "Apple II LoRes (High Color)", "Apple II lo-res 15 colors"),
    ("APPLE2_HIRES", "Apple II HiRes (Low Color)", "Apple II hi-res 6 colors"),
    ("ATARI2600", "Atari 2600", "Atari 2600 NTSC palette"),
    ("C64", "Commodore 64", "C64 Colodore 16 colors"),
    ("NES", "Famicom / NES", "NES 2C02 palette"),
    ("GAMEBOY", "Gameboy", "Game Boy DMG 4 shades"),
    ("GAMEBOY_COLOR", "Gameboy Color — Stylized 32", "Curated 32-color RGB555-valid GBC presentation palette"),
    ("MASTER_SYSTEM", "Master System", "Sega Master System 6-bit RGB (64 colors)"),
    ("WEB", "Web Color", "Web-safe 216 colors"),
    # add-on extras (not from the Substance spec; sources in
    # THIRD_PARTY_NOTICES.md) ---------------------------------------------
    ("ZX_SPECTRUM", "ZX Spectrum", "ZX Spectrum 15 colors"),
    ("AMSTRAD_CPC", "Amstrad CPC", "Amstrad CPC 27-color cube"),
    ("MSX", "MSX", "MSX TMS9918 15 colors"),
    ("VIC20", "VIC-20", "Commodore VIC-20 16 colors"),
    ("CGA", "CGA / EGA", "CGA / EGA default 16 colors"),
    ("BBC_MICRO", "BBC Micro", "BBC Micro 8 colors"),
    ("SNES", "SNES — Stylized 32", "Curated 32-color RGB555-valid SNES presentation palette"),
    ("GENESIS", "Genesis / Mega Drive", "Sega Genesis 9-bit color reduction"),
    ("APPLE_IIGS", "Apple IIGS", "Apple IIGS 12-bit color reduction"),
    ("PICO8", "PICO-8", "PICO-8 fantasy console 16 colors"),
    ("TIC80", "TIC-80 / Sweetie 16", "TIC-80 uses the Sweetie-16 16-color palette"),
    ("DB32", "DawnBringer 32", "DawnBringer's 32-color palette"),
    ("RESURRECT64", "Resurrect 64", "Resurrect 64-color palette"),
    ("ENDESGA32", "Endesga 32", "Endesga 32-color palette"),
    ("ENDESGA16", "Endesga 16", "Endesga 16-color palette"),
    ("GRAYSCALE_2", "Grayscale 2", "2-step grayscale ramp"),
    ("GRAYSCALE_4", "Grayscale 4", "4-step grayscale ramp"),
    ("GRAYSCALE_8", "Grayscale 8", "8-step grayscale ramp"),
    ("GRAYSCALE_16", "Grayscale 16", "16-step grayscale ramp"),
]


PALETTE_EXTRACT_METHODS = [
    ("KMEANS", "K-means", "Iterative perceptual palette extraction"),
    ("FREQUENCY", "Frequency", "Most frequent exact display colors"),
    ("EXACT", "Exact Colors", "Unique colors ordered by frequency"),
    ("RAMPS", "Color Ramps", "Hue families of dark-to-light shades with pixel-art hue shifting"),
]


PALETTE_SORT_MODES = [
    ("NONE", "Original Order", "Leave palette entry order unchanged"),
    ("LUMINANCE", "Luminance", "Sort from dark to bright"),
    ("HUE", "Hue", "Sort by hue, saturation, then value"),
    ("SATURATION", "Saturation", "Sort by saturation, value, then hue"),
    ("RGB", "RGB", "Sort by red, green, then blue"),
]


FINISH_MASK_TYPES = [
    ("NONE", "None", "Apply finishing everywhere"),
    ("EDGES", "Edges", "Finish only high-frequency edges"),
    ("FLATS", "Flats", "Finish only flat areas"),
    ("LUMINANCE", "Luminance Range", "Finish inside the luminance band"),
    ("SATURATION", "Saturation Range", "Finish inside the saturation band"),
    ("GRADIENT", "Gradient", "Finish along a positional gradient"),
    ("RADIAL", "Radial", "Finish from the image center outward"),
    ("CUSTOM", "Custom Mask", "Finish through the custom mask image"),
]


CHANNEL_MASKS = [
    ("RGB", "RGB", "Apply to all color channels"),
    ("R", "Red", "Apply to red only"),
    ("G", "Green", "Apply to green only"),
    ("B", "Blue", "Apply to blue only"),
    ("RG", "Red + Green", "Apply to red and green"),
    ("RB", "Red + Blue", "Apply to red and blue"),
    ("GB", "Green + Blue", "Apply to green and blue"),
]


POSTERIZE_RANGE_MODES = [
    ("FULL", "Full 0–1 Range", "Use the complete display range"),
    ("MIN_MAX", "Image Min / Max", "Fit levels to the image's per-channel range"),
    ("PERCENTILE", "Robust Percentile", "Ignore configurable shadow and highlight outliers"),
]


ALPHA_POLICIES = [
    ("PRESERVE", "Preserve Alpha", "Leave source alpha untouched"),
    ("REPLACE", "Replace Alpha", "Use the stage result alpha when one is available"),
    ("QUANTIZE", "Quantize Alpha", "Clamp the stage result alpha to display range"),
]


V3_STAGE_ITEMS = [
    ("pixelate", "Pixelate", "Build the coherent pixel grid"),
    ("posterize", "Posterize / Levels", "Apply explicit per-channel levels"),
    ("shading", "Tone Bands", "Shade with a few flat tones (cel look)"),
    ("dither", "Dither", "Apply an ordered/noise/palette threshold pattern"),
    ("quantize", "Quantize", "Apply palette, LUT, or per-channel reduction"),
    ("sprite", "Sprite Cleanup / Outline", "Remove stray cells and outline the silhouette"),
    ("display_finish", "Display Finish", "Apply the optional CRT/display finish stack"),
]


V3_PALETTE_LOCKS = [
    ("OFF", "Off", "Allow finishing to create new colors"),
    ("SNAP_BACK", "Index Guard", "Re-snap the finished result to the active palette"),
    ("PALETTE_TINT", "Palette Tint", "Style palette entries, then preserve their indices"),
]


V3_GRID_COHERENCE = [
    ("OFF", "Off", "Allow full-resolution effects"),
    ("DITHER_CELL", "Dither per Cell", "Use one dither threshold for each pixel cell"),
    ("FINAL_CELL", "Final Cell", "Collapse the finished image back to the pixel grid"),
]
