"""PixelatorPlus settings: the unified Pixel8r-derived feature surface.

The add-on starts with the latest v2.72-style defaults, while exposing useful
controls reconstructed from every documented Pixel8r release.  It deliberately
has no compatibility-version selector: artists can combine all capabilities.
The nested v3 settings add the canonical stage policy and PixelatorPlus-native
palette/grid controls without breaking the flat compatibility surface.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    IntVectorProperty,
    CollectionProperty,
    PointerProperty,
    StringProperty,
)

from .presets import PRESET_ITEMS


# collect_params() resolves "//" paths itself.  Newer Blender versions warn
# unless a path property declares that; older ones reject the unknown option
# at registration, so the option is feature-tested.
_BLEND_RELATIVE_PATH_OPTIONS = {"ANIMATABLE"} | (
    {"PATH_SUPPORTS_BLEND_RELATIVE"}
    if "is_path_supports_blend_relative" in bpy.types.Property.bl_rna.properties
    else set()
)


def _mark_dirty(self, context):
    """Property update hook: ask the live preview to recompute (debounced)."""
    try:
        from . import preview

        preview.mark_dirty(context)
    except Exception:
        pass  # preview must never break property edits


_DITHER_TYPES = [
    ("NONE", "None", "No dithering"),
    ("WHITE_NOISE", "White Noise", "Seeded white-noise threshold map"),
    ("BLUE_NOISE", "Blue Noise", "Tileable blue-noise threshold map"),
    ("BAYER", "Bayer", "8x8 ordered Bayer matrix"),
    ("PATTERN", "Pattern", "Built-in 8x8 clustered-dot pattern"),
    ("CUSTOM", "Custom Dither Pattern", "Custom dither texture (any square resolution)"),
    ("CUSTOM_8X8", "Custom Dither 8x8 px", "Custom dither texture fixed at 8x8 pixels"),
    ("CUSTOM_16X16", "Custom Dither 16x16 px", "Custom dither texture fixed at 16x16 pixels"),
    ("AMOGUS", "Amogus", "Crewmate threshold pattern"),
    # -- add-on extras (not from the Substance spec) ------------------------
    ("BAYER_2X2", "Bayer 2x2", "2x2 ordered Bayer matrix"),
    ("BAYER_4X4", "Bayer 4x4", "4x4 ordered Bayer matrix"),
    ("HALFTONE_DOT", "Halftone Dot", "45-degree halftone dot screen"),
    ("HALFTONE_LINE", "Halftone Line", "Diagonal halftone line screen"),
    ("CROSSHATCH", "Crosshatch", "Two perpendicular halftone line screens"),
    ("SUZANNE", "Suzanne", "Blender monkey threshold pattern — our own mascot dither"),
]

_BLEND_MODES = [
    ("OVERLAY", "Overlay", "Overlay blend in sRGB space"),
    ("OVERLAY_LINEAR", "Overlay (Linear)", "Overlay blend in linear light"),
    ("SOFT_LIGHT", "Soft Light", "Soft-light blend in sRGB space"),
    ("SOFT_LIGHT_LINEAR", "Soft Light (Linear)", "Soft-light blend in linear light"),
]

_DITHER_STRATEGIES = [
    ("OVERLAY", "Texture Overlay", "Blend the threshold map into the image before quantization"),
    ("PALETTE_THRESHOLD", "Palette Threshold", "Choose between the two nearest palette colors using the threshold map"),
]

_SCALE_ALGORITHMS = [
    ("NEAREST", "Nearest", "Keep ordinary nearest-neighbor pixel blocks"),
    ("SCALE2X", "Scale2x", "Edge-aware 2x pixel-art scaling"),
    ("SCALE3X", "Scale3x", "Edge-aware 3x pixel-art scaling"),
    ("CLEANEDGE", "CleanEdge", "Tolerance-aware CleanEdge-style 2x scaling"),
    ("CONTENT_AWARE", "Content Aware", "Capped seam-carving reconstruction for small grids"),
]

_MASK_TYPES = [
    ("NONE", "None", "Dither everywhere (v2.72 default)"),
    ("EDGES", "Dither by Edges", "Dither only detailed/edge areas"),
    ("FLATS", "Dither by Flats", "Dither only flat areas"),
    ("CUSTOM", "Custom Dither Mask Texture", "Use a custom mask image"),
    # -- add-on extras (not from the Substance spec) ------------------------
    ("LUMINANCE", "Luminance Range", "Dither only a luminance band"),
    ("SATURATION", "Saturation Range", "Dither only a saturation band"),
    ("GRADIENT", "Gradient Ramp", "Positional ramp mask at a configurable angle"),
    ("RADIAL", "Radial Falloff", "Dither falls off from the image center"),
]

# v2.72 relabels the LUT quantize mode "Lookup Table / Palette"
_QUANTIZE_TYPES = [
    ("NONE", "None", "No color quantization"),
    ("CUSTOM_PALETTE", "Generated Palette",
     "Extract a palette from the image in the chosen color space (slower)"),
    ("PER_CHANNEL", "Per Channel",
     "Reduce each channel to N colors / bits"),
    ("LUT", "Palette / LUT",
     "Snap to a built-in vintage palette, a custom 4K LUT, or a custom palette image"),
]

_INIT_MODES = [
    ("1", "Mode 1", "Random pixel initialization"),
    ("2", "Mode 2", "K-means++ initialization"),
    ("3", "Mode 3", "Luminance-spaced initialization"),
    ("4", "Mode 4", "Unique-color initialization"),
]

_COLOR_MODES = [
    ("RGB", "RGB", "Cluster in RGB"),
    ("CIELAB", "CIELAB", "Cluster in CIELAB (perceptual)"),
    ("OKLAB", "Oklab", "Cluster in Oklab (perceptual)"),
]

_APPLY_MODES = [
    ("RGB", "RGB", "Match palette colors in RGB"),
    ("CIELAB", "CIELAB", "Match palette colors in CIELAB"),
    ("OKLAB", "Oklab", "Match palette colors in Oklab"),
]

_FORCE_COLORS = [
    ("NONE", "None", "No forced colors"),
    ("DARKEST_BRIGHTEST", "Darkest Brightest", "Force the darkest and brightest image colors into the palette"),
    ("BLACK_WHITE", "Black White", "Force pure black and pure white into the palette"),
]

_LUTS = [
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
    # -- add-on extras (not from the Substance spec; sources in
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

_PALETTE_EXTRACT_METHODS = [
    ("KMEANS", "K-means", "Iterative perceptual palette extraction"),
    ("FREQUENCY", "Frequency", "Most frequent exact display colors"),
    ("EXACT", "Exact Colors", "Unique colors ordered by frequency"),
]

_PALETTE_SORT_MODES = [
    ("NONE", "Original Order", "Leave palette entry order unchanged"),
    ("LUMINANCE", "Luminance", "Sort from dark to bright"),
    ("HUE", "Hue", "Sort by hue, saturation, then value"),
    ("SATURATION", "Saturation", "Sort by saturation, value, then hue"),
    ("RGB", "RGB", "Sort by red, green, then blue"),
]

_FINISH_MASK_TYPES = [
    ("NONE", "None", "Apply finishing everywhere"),
    ("EDGES", "Edges", "Finish only high-frequency edges"),
    ("FLATS", "Flats", "Finish only flat areas"),
    ("LUMINANCE", "Luminance Range", "Finish inside the luminance band"),
    ("SATURATION", "Saturation Range", "Finish inside the saturation band"),
    ("GRADIENT", "Gradient", "Finish along a positional gradient"),
    ("RADIAL", "Radial", "Finish from the image center outward"),
    ("CUSTOM", "Custom Mask", "Finish through the custom mask image"),
]

_CHANNEL_MASKS = [
    ("RGB", "RGB", "Apply to all color channels"),
    ("R", "Red", "Apply to red only"),
    ("G", "Green", "Apply to green only"),
    ("B", "Blue", "Apply to blue only"),
    ("RG", "Red + Green", "Apply to red and green"),
    ("RB", "Red + Blue", "Apply to red and blue"),
    ("GB", "Green + Blue", "Apply to green and blue"),
]

_POSTERIZE_RANGE_MODES = [
    ("FULL", "Full 0–1 Range", "Use the complete display range"),
    ("MIN_MAX", "Image Min / Max", "Fit levels to the image's per-channel range"),
    ("PERCENTILE", "Robust Percentile", "Ignore configurable shadow and highlight outliers"),
]

_ALPHA_POLICIES = [
    ("PRESERVE", "Preserve Alpha", "Leave source alpha untouched"),
    ("REPLACE", "Replace Alpha", "Use the stage result alpha when one is available"),
    ("QUANTIZE", "Quantize Alpha", "Clamp the stage result alpha to display range"),
]

V3_STAGE_ITEMS = [
    ("pixelate", "Pixelate", "Build the coherent pixel grid"),
    ("posterize", "Posterize / Levels", "Apply explicit per-channel levels"),
    ("dither", "Dither", "Apply an ordered/noise/palette threshold pattern"),
    ("quantize", "Quantize", "Apply palette, LUT, or per-channel reduction"),
    ("sprite", "Sprite Cleanup / Outline", "Remove stray cells and outline the silhouette"),
    ("display_finish", "Display Finish", "Apply the optional CRT/display finish stack"),
]

_V3_PALETTE_LOCKS = [
    ("OFF", "Off", "Allow finishing to create new colors"),
    ("SNAP_BACK", "Index Guard", "Re-snap the finished result to the active palette"),
    ("PALETTE_TINT", "Palette Tint", "Style palette entries, then preserve their indices"),
]

_V3_GRID_COHERENCE = [
    ("OFF", "Off", "Allow full-resolution effects"),
    ("DITHER_CELL", "Dither per Cell", "Use one dither threshold for each pixel cell"),
    ("FINAL_CELL", "Final Cell", "Collapse the finished image back to the pixel grid"),
]


class PixelatorPlusV3Stage(bpy.types.PropertyGroup):
    stage_id: EnumProperty(name="Stage", items=V3_STAGE_ITEMS, options={"HIDDEN"})
    enabled: BoolProperty(name="Enabled", default=True, update=_mark_dirty)


class PixelatorPlusV3Settings(bpy.types.PropertyGroup):
    """Canonical settings for additive v3 policies and the stage stack."""

    palette_lock: EnumProperty(
        name="Palette Lock", default="OFF", items=_V3_PALETTE_LOCKS,
        update=_mark_dirty,
        description="PixelatorPlus-exclusive guard for preserving palette identity through finishing",
    )
    palette_lock_strength: FloatProperty(
        name="Palette Tint Strength", default=1.0, min=0.0, max=1.0,
        subtype="FACTOR", update=_mark_dirty,
        description="Blend between the source palette and its display-tinted version",
    )
    grid_coherence: EnumProperty(
        name="Grid Coherence", default="OFF", items=_V3_GRID_COHERENCE,
        update=_mark_dirty,
        description="Keep dither and finishing aligned with the selected pixel grid",
    )
    stage_stack: CollectionProperty(type=PixelatorPlusV3Stage)


class PixelatorPlusSettings(bpy.types.PropertyGroup):
    # -- image pins ---------------------------------------------------------
    input_image: PointerProperty(
        name="Input", type=bpy.types.Image, update=_mark_dirty,
        description="Source image to pixelate",
    )
    v3: PointerProperty(
        name="V3 Settings", type=PixelatorPlusV3Settings,
        description="Canonical PixelatorPlus v3 policies and stage stack",
    )
    custom_dither_image: PointerProperty(
        name="Custom Dither Pattern", type=bpy.types.Image, update=_mark_dirty,
        description="Custom dither pattern (any square resolution)",
    )
    custom_mask_image: PointerProperty(
        name="Custom Dither Mask", type=bpy.types.Image, update=_mark_dirty,
        description="Custom dither mask texture",
    )
    custom_lut_image: PointerProperty(
        name="Custom LUT", type=bpy.types.Image, update=_mark_dirty,
        description="Custom 4096x4096 LUT image",
    )
    custom_palette_image: PointerProperty(
        name="Custom Palette", type=bpy.types.Image, update=_mark_dirty,
        description="Custom palette image (opaque unique colors only; maximum 256)",
    )
    # Named v3 maps keep the advanced workflow expressive without adding an
    # image socket to every scalar control.
    strength_map_image: PointerProperty(
        name="Strength Map", type=bpy.types.Image, update=_mark_dirty,
        description="Optional image controlling dither, finish, and stage strength",
    )
    threshold_map_image: PointerProperty(
        name="Threshold Map", type=bpy.types.Image, update=_mark_dirty,
        description="Optional image modulating palette-threshold dither",
    )
    range_map_image: PointerProperty(
        name="Range Map", type=bpy.types.Image, update=_mark_dirty,
        description="Optional image controlling local Posterize/Levels amount",
    )

    # -- Dimensions ----------------------------------------------------------
    use_separate_pixel_count: BoolProperty(
        name="Separate XY Pixel Count", default=False, update=_mark_dirty,
        description="Enable non-square pixel counts",
    )
    square_pixel_count: IntProperty(
        name="Square Pixel Count", default=256, min=0, max=2048, update=_mark_dirty,
        description="Pixel count on the shortest image axis",
    )
    pixel_count_x: IntProperty(
        name="Pixel Count X", default=256, min=0, max=2048, update=_mark_dirty,
    )
    pixel_count_y: IntProperty(
        name="Pixel Count Y", default=256, min=0, max=2048, update=_mark_dirty,
    )

    # -- Pixelate Style ------------------------------------------------------
    downscale_mode: EnumProperty(
        name="Downscale Mode", default="NEAREST", update=_mark_dirty,
        items=[
            ("NEAREST", "Nearest Neighbor", "Hard blocky pixels"),
            ("NEAREST_SOFTER", "Nearest Softer", "Area-averaged block colors"),
        ],
    )
    scale_algorithm: EnumProperty(
        name="Pixel-Art Scale Algorithm", default="NEAREST", items=_SCALE_ALGORITHMS,
        update=_mark_dirty,
        description="Optional edge-aware algorithm applied to the small pixel grid before final nearest upscaling",
    )
    scale_tolerance: FloatProperty(
        name="Scale Tolerance", default=0.05, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
        description="Color difference tolerated by Scale2x, Scale3x, and CleanEdge",
    )
    content_aware_factor: FloatProperty(
        name="Content-Aware Factor", default=1.0, min=0.25, max=4.0,
        update=_mark_dirty,
        description="Target scale factor for the capped content-aware grid resize",
    )
    content_aware_max_dimension: IntProperty(
        name="Content-Aware Work Limit", default=128, min=16, max=512,
        update=_mark_dirty,
        description="Maximum working dimension before content-aware scaling falls back to nearest",
    )
    content_aware_seam_mode: EnumProperty(
        name="Content-Aware Seam", default="MINIMUM", update=_mark_dirty,
        items=[
            ("MINIMUM", "Protect Edges", "Remove low-energy seams first"),
            ("MAXIMUM", "Favor Edges", "Remove high-energy seams first for an abstract effect"),
        ],
    )
    filter_preview: EnumProperty(
        name="Preview Texture Filtering", default="NONE", update=_mark_dirty,
        description="Viewport preview filtering only — never applied on Apply/Export",
        items=[
            ("NONE", "None", "Nearest (pixel-perfect)"),
            ("BILINEAR", "Bilinear", "Bilinear smoothing of the pixel grid"),
            ("N64_3POINT", "N64 3-Point", "Nintendo 64 three-point filtering"),
        ],
    )

    # -- Dithering -----------------------------------------------------------
    dither_type: EnumProperty(
        name="Dither Type", default="NONE", items=_DITHER_TYPES, update=_mark_dirty,
    )
    dither_strategy: EnumProperty(
        name="Dither Strategy", default="OVERLAY", items=_DITHER_STRATEGIES,
        update=_mark_dirty,
        description="Use a texture overlay or palette-aware threshold selection",
    )
    custom_dither_resolution: IntVectorProperty(
        name="Custom Dither Resolution", size=2, default=(8, 8), min=0, max=10,
        update=_mark_dirty,
        description="Custom dither tile size as a power of two per axis (8 = 256 px)",
    )
    dither_blend_mode: EnumProperty(
        name="Blend Mode", default="SOFT_LIGHT", items=_BLEND_MODES, update=_mark_dirty,
    )
    use_gray_dither: BoolProperty(
        name="Grayscale Dither", default=False, update=_mark_dirty,
        description="Use the pattern's red channel as a grayscale dither",
    )
    dither_strength: FloatProperty(
        name="Blend Strength", default=0.25, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
    )
    dither_saturation: FloatProperty(
        name="Blend Saturation", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
    )
    palette_dither_contrast: FloatProperty(
        name="Palette Dither Contrast", default=1.0, min=0.0, max=4.0,
        update=_mark_dirty,
        description="Expand or compress the palette-boundary threshold response",
    )
    palette_dither_invert: BoolProperty(
        name="Invert Palette Threshold", default=False, update=_mark_dirty,
    )
    lock_dither_to_grid: BoolProperty(
        name="Lock Dither to Pixel Grid", default=False, update=_mark_dirty,
        description="Generate one dither threshold per pixel-grid cell before nearest upscaling",
    )
    dither_mask_type: EnumProperty(
        name="Dither Mask Type", default="NONE", items=_MASK_TYPES, update=_mark_dirty,
    )
    dither_cutoff: FloatProperty(
        name="Dither Mask Strength", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
    )
    dither_mask_gamma: FloatProperty(
        name="Dither Mask Gamma", default=1.0, min=0.1, max=4.0, update=_mark_dirty,
    )
    preview_dither_mask: BoolProperty(
        name="Preview Dither Mask", default=False, update=_mark_dirty,
        description="Output the dither mask instead of the image",
    )
    # -- mask shaping extras (not from the Substance spec) ------------------
    dither_mask_lum_low: FloatProperty(
        name="Luminance Low", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty, description="Lower edge of the luminance band mask",
    )
    dither_mask_lum_high: FloatProperty(
        name="Luminance High", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty, description="Upper edge of the luminance band mask",
    )
    dither_mask_sat_low: FloatProperty(
        name="Saturation Low", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty, description="Lower edge of the saturation band mask",
    )
    dither_mask_sat_high: FloatProperty(
        name="Saturation High", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty, description="Upper edge of the saturation band mask",
    )
    dither_mask_gradient_angle: FloatProperty(
        name="Gradient Angle", default=0.0, min=0.0, max=360.0, update=_mark_dirty,
        description="Direction of the gradient ramp mask in degrees (0 = left to right, 90 = top to bottom)",
    )
    dither_mask_invert: BoolProperty(
        name="Invert Mask", default=False, update=_mark_dirty,
        description="Invert the final dither mask",
    )
    dither_mask_blur: IntProperty(
        name="Blur Mask", default=0, min=0, max=64, update=_mark_dirty,
        description="Soften the final dither mask by this many pixels (0 = off)",
    )
    show_mask_controls: BoolProperty(
        name="Frequency Weights", default=False, update=_mark_dirty,
        description="Show per-frequency weights for the edge and flat masks",
    )
    huge: FloatProperty(name="Huge", default=1.0, min=0.0, max=1.0, update=_mark_dirty)
    big: FloatProperty(name="Big", default=1.0, min=0.0, max=1.0, update=_mark_dirty)
    large: FloatProperty(name="Large", default=0.8, min=0.0, max=1.0, update=_mark_dirty)
    medium: FloatProperty(name="Medium", default=0.6, min=0.0, max=1.0, update=_mark_dirty)
    fine: FloatProperty(name="Fine", default=0.4, min=0.0, max=1.0, update=_mark_dirty)
    sharp: FloatProperty(name="Sharp", default=0.2, min=0.0, max=1.0, update=_mark_dirty)
    pixel_perfect: FloatProperty(
        name="Pixel Perfect", default=0.2, min=0.0, max=1.0, update=_mark_dirty,
    )

    # -- Quantization --------------------------------------------------------
    quantize_type: EnumProperty(
        name="Quantization Type", default="NONE", items=_QUANTIZE_TYPES,
        update=_mark_dirty,
    )
    posterize_enabled: BoolProperty(
        name="Enable Posterize / Levels", default=False, update=_mark_dirty,
        description="Quantize each channel to explicit display levels before dithering",
    )
    posterize_levels: IntProperty(
        name="Levels per Channel", default=8, min=2, max=256, update=_mark_dirty,
        description="Number of output steps per RGB channel",
    )
    posterize_range_mode: EnumProperty(
        name="Level Range", default="FULL", items=_POSTERIZE_RANGE_MODES,
        update=_mark_dirty,
    )
    posterize_range_low: FloatProperty(
        name="Input Black", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
    )
    posterize_range_high: FloatProperty(
        name="Input White", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
    )
    posterize_percentile_low: FloatProperty(
        name="Shadow Percentile", default=2.0, min=0.0, max=49.0,
        update=_mark_dirty,
    )
    posterize_percentile_high: FloatProperty(
        name="Highlight Percentile", default=98.0, min=51.0, max=100.0,
        update=_mark_dirty,
    )
    posterize_gamma: FloatProperty(
        name="Posterize Gamma", default=1.0, min=0.1, max=4.0, update=_mark_dirty,
        description="Move level thresholds while retaining input endpoints",
    )
    posterize_mix: FloatProperty(
        name="Posterize Mix", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
    )
    posterize_channel_mask: EnumProperty(
        name="Posterize Channels", default="RGB", items=_CHANNEL_MASKS, update=_mark_dirty,
    )
    posterize_alpha_policy: EnumProperty(
        name="Posterize Alpha", default="PRESERVE", items=_ALPHA_POLICIES, update=_mark_dirty,
    )
    # error diffusion is an add-on extra (not from the Substance spec)
    diffusion: EnumProperty(
        name="Error Diffusion", default="NONE", update=_mark_dirty,
        description="Diffuse quantization error across neighboring pixels at "
        "pixel-grid resolution (classic Macintosh/newspaper look)",
        items=[
            ("NONE", "None", "Plain nearest-color quantization"),
            ("FLOYD_STEINBERG", "Floyd-Steinberg", "Classic 4-neighbor error diffusion"),
            ("ATKINSON", "Atkinson", "6-neighbor diffusion, lighter mid-tones (1-bit Macintosh look)"),
            ("SIERRA_LITE", "Sierra Lite", "3-neighbor diffusion, a softer Floyd-Steinberg"),
            ("JJN", "Jarvis-Judice-Ninke", "Broad 12-neighbor diffusion for smooth ramps"),
            ("LINEAR", "Linear", "Carry error along the scan direction for line-art ramps"),
        ],
    )
    diffusion_strength: FloatProperty(
        name="Diffusion Strength", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
        description="How much quantization error propagates to neighbors",
    )
    diffusion_serpentine: BoolProperty(
        name="Serpentine Scan", default=True, update=_mark_dirty,
        description="Alternate scan direction on each row to reduce directional bias",
    )
    initialize_mode: EnumProperty(
        name="Initialization Mode", default="1", items=_INIT_MODES, update=_mark_dirty,
        description="Palette initial-color strategy",
    )
    color_mode: EnumProperty(
        name="Build Space", default="RGB", items=_COLOR_MODES,
        update=_mark_dirty,
        description="Color space in which the palette is generated",
    )
    apply_palette_mode: EnumProperty(
        name="Match Space", default="RGB", items=_APPLY_MODES,
        update=_mark_dirty,
        description="Color space used to match each pixel to its nearest palette color",
    )
    quantize_quality: IntProperty(
        name="Quality", default=2, min=0, max=8, update=_mark_dirty,
        description="Palette-generation quality (sample count and iterations)",
    )
    quantize_seed: FloatProperty(
        name="Initial Random Seed", default=1.0, min=0.0, max=10.0, update=_mark_dirty,
        description="Explicit palette-generation seed; uses Random Seed when disabled",
    )
    use_explicit_quantize_seed: BoolProperty(
        name="Use Explicit Palette Seed", default=False, update=_mark_dirty,
        description="Use Initial Random Seed instead of the shared Random Seed",
    )
    chroma_importance: FloatProperty(
        name="Color Importance", default=35.0, min=0.0, max=50.0, update=_mark_dirty,
        description="Palette chroma weighting reconstruction; neutral when disabled",
    )
    use_chroma_importance: BoolProperty(
        name="Use Color Importance", default=False, update=_mark_dirty,
        description="Enable the Color Importance palette weighting control",
    )
    use_pixelated_for_quantize: BoolProperty(
        name="Sample Pixel Grid", default=False, update=_mark_dirty,
        description="Build the palette from the downscaled pixel grid instead of the full image",
    )
    palette_extract_method: EnumProperty(
        name="Palette Extraction", default="KMEANS", items=_PALETTE_EXTRACT_METHODS,
        update=_mark_dirty,
        description="How generated palettes are extracted from the image",
    )
    palette_sort_mode: EnumProperty(
        name="Palette Sort", default="NONE", items=_PALETTE_SORT_MODES,
        update=_mark_dirty,
    )
    palette_shift: IntProperty(
        name="Palette Shift", default=0, min=-256, max=256, update=_mark_dirty,
        description="Cyclically rotate palette entries after extraction",
    )
    palette_trim: BoolProperty(
        name="Trim Duplicate Colors", default=False, update=_mark_dirty,
        description="Remove near-duplicate entries after palette extraction",
    )
    palette_replace_image: PointerProperty(
        name="Replacement Palette", type=bpy.types.Image, update=_mark_dirty,
        description="Optional palette image used to replace nearby extracted colors",
    )
    palette_replace_threshold: FloatProperty(
        name="Replacement Threshold", default=0.1, min=0.0, max=1.0,
        subtype="FACTOR", update=_mark_dirty,
    )
    k_num_colors: IntProperty(
        name="Number of Colors", default=32, min=2, max=256, update=_mark_dirty,
    )
    gamma: FloatProperty(
        name="Palette Gamma", default=1.0, min=0.1, max=4.0,
        update=_mark_dirty,
        description="Gamma applied before palette generation; raise it to preserve dark tones",
    )
    force_colors: EnumProperty(
        name="Force Colors", default="NONE", items=_FORCE_COLORS, update=_mark_dirty,
    )
    output_palette: BoolProperty(
        name="Output Palette", default=False,
        description="Also produce a palette swatch image on Apply",
    )
    output_lut: BoolProperty(
        name="Output Palette LUT", default=False,
        description="Also produce a 4096x4096 LUT image of the palette on Apply (slow)",
    )
    use_range_adaptive: BoolProperty(
        name="Use Range Adaptive Mode", default=False, update=_mark_dirty,
    )
    quantize_colors_or_bits: EnumProperty(
        name="Color Mode", default="COLORS", update=_mark_dirty,
        items=[
            ("COLORS", "Colors Per Channel", "Exact level count per channel"),
            ("BITS", "Bits Per Channel", "Bit depth per channel"),
        ],
    )
    quantize_colors: IntProperty(
        name="Colors Per Channel", default=256, min=2, max=256, update=_mark_dirty,
    )
    quantize_bits: IntProperty(
        name="Bits Per Channel", default=8, min=1, max=8, update=_mark_dirty,
    )
    output_default_lut: BoolProperty(
        name="Output Identity LUT", default=False,
        description="Also produce the identity 4096x4096 LUT on Apply",
    )
    lut: EnumProperty(
        name="LUT", default="AMIGA", items=_LUTS, update=_mark_dirty,
    )
    cube_lut_path: StringProperty(
        name=".cube LUT File", default="", subtype="FILE_PATH", update=_mark_dirty,
        options=_BLEND_RELATIVE_PATH_OPTIONS,
        description="Path to a portable 3D .cube LUT",
    )
    cube_lut_interpolation: EnumProperty(
        name=".cube Interpolation", default="TRILINEAR", update=_mark_dirty,
        items=[
            ("TRILINEAR", "Trilinear", "Smooth interpolation through the 3D LUT"),
            ("NEAREST", "Nearest", "Nearest lattice point for hard stepped looks"),
        ],
    )
    cube_lut_strength: FloatProperty(
        name=".cube Strength", default=1.0, min=0.0, max=1.0,
        subtype="FACTOR", update=_mark_dirty,
    )

    # -- Sprite (add-on extra, PixelatorPlus-native) --------------------------
    sprite_cleanup: BoolProperty(
        name="Remove Stray Pixels", default=False, update=_mark_dirty,
        description="Replace isolated cells with the color their neighbors agree on",
    )
    sprite_cleanup_agreement: IntProperty(
        name="Neighbor Agreement", default=3, min=2, max=4, update=_mark_dirty,
        description="How many of a stray cell's four neighbors must share a color "
        "before it is replaced (4 = only fully surrounded cells)",
    )
    sprite_outline: EnumProperty(
        name="Outline", default="NONE", update=_mark_dirty,
        description="Draw a one-cell outline around transparent-background silhouettes",
        items=[
            ("NONE", "None", "No outline"),
            ("OUTSIDE", "Outside", "Fill empty cells around the silhouette"),
            ("INSIDE", "Inside", "Recolor the silhouette's own edge cells"),
        ],
    )
    sprite_part_lines: BoolProperty(
        name="Part Lines", default=False, update=_mark_dirty,
        description="Draw one-pixel lines where the model's parts meet (needs an ID map)",
    )
    sprite_part_source: EnumProperty(
        name="Parts", default="OBJECT", update=_mark_dirty,
        items=[
            ("OBJECT", "Objects", "Each object is one part"),
            ("MATERIAL", "Materials", "Each material is one part"),
        ],
        description="What counts as one part when an ID map is rendered",
    )
    id_map_image: PointerProperty(
        name="ID Map", type=bpy.types.Image, update=_mark_dirty,
        description="Flat per-part color render with the same framing as the input "
        "(Render ID Map creates one; sprite sheets render their own)",
    )
    sprite_outline_color_mode: EnumProperty(
        name="Line Color", default="SELECTIVE", update=_mark_dirty,
        description="Color of outlines and part lines",
        items=[
            ("SELECTIVE", "Selective", "Darken the neighboring sprite color (pixel-art sel-out)"),
            ("DARKEST", "Darkest Palette Color", "Use the darkest color of the active palette"),
            ("CUSTOM", "Custom", "Use a fixed outline color"),
        ],
    )
    sprite_outline_color: FloatVectorProperty(
        name="Custom Line Color", size=3, default=(0.05, 0.05, 0.08), min=0.0, max=1.0,
        subtype="COLOR_GAMMA", update=_mark_dirty,
        description="Fixed outline color (snapped to the palette when one is active)",
    )
    sprite_outline_darken: FloatProperty(
        name="Darken", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
        description="How much darker than the sprite selective lines are",
    )
    sprite_outline_corners: BoolProperty(
        name="Outline Corners", default=False, update=_mark_dirty,
        description="Also outline diagonal neighbors for a heavier, rounder outline",
    )
    sprite_alpha_threshold: FloatProperty(
        name="Opacity Threshold", default=0.5, min=0.01, max=1.0, subtype="FACTOR",
        update=_mark_dirty,
        description="Cells at least this opaque count as part of the sprite",
    )

    # -- Sprite sheet (animation export workflow, not part of the look) -----
    sheet_use_scene_range: BoolProperty(
        name="Use Scene Frame Range", default=True,
        description="Render the scene's start-to-end frames",
    )
    sheet_frame_start: IntProperty(name="Start", default=1, min=0)
    sheet_frame_end: IntProperty(name="End", default=24, min=0)
    sheet_frame_step: IntProperty(
        name="Step", default=1, min=1, max=100,
        description="Render every Nth frame",
    )
    sheet_layout: EnumProperty(
        name="Layout", default="GRID",
        items=[
            ("GRID", "Grid", "Rows and columns"),
            ("ROW", "Row", "One horizontal strip"),
            ("COLUMN", "Column", "One vertical strip"),
        ],
    )
    sheet_columns: IntProperty(
        name="Columns", default=0, min=0, max=256,
        description="Frames per row (0 = automatic, near square)",
    )
    sheet_spacing: IntProperty(
        name="Spacing", default=0, min=0, max=64,
        description="Transparent pixels between frames",
    )
    sheet_padding: IntProperty(
        name="Padding", default=0, min=0, max=64,
        description="Transparent pixels around the whole sheet",
    )
    sheet_pixel_scale: IntProperty(
        name="Pixel Scale", default=1, min=1, max=16,
        description="Output pixels per sprite pixel (1 = native resolution)",
    )
    sheet_trim: BoolProperty(
        name="Trim Empty Space", default=False,
        description="Crop every frame to the area any frame uses, keeping the animation aligned",
    )
    sheet_skip_empty: BoolProperty(
        name="Skip Empty Frames", default=False,
        description="Leave fully transparent frames out of the sheet",
    )
    sheet_shared_palette: BoolProperty(
        name="Shared Palette", default=True,
        description="Generate one palette from all frames so colors never flicker "
        "(Generated Palette mode)",
    )
    sheet_transparent: BoolProperty(
        name="Transparent Background", default=True,
        description="Render with Film > Transparent for the duration of the sheet",
    )
    last_sheet_name: StringProperty(name="Last Sprite Sheet", default="")

    # -- Display finishing --------------------------------------------------
    finish_enabled: BoolProperty(
        name="Enable Display Finish", default=False, update=_mark_dirty,
        description="Apply the post-quantization display finishing stack",
    )
    finish_brightness: FloatProperty(name="Brightness", default=0.0, min=-1.0, max=1.0, update=_mark_dirty)
    finish_contrast: FloatProperty(name="Contrast", default=1.0, min=0.0, max=4.0, update=_mark_dirty)
    finish_exposure: FloatProperty(name="Exposure", default=0.0, min=-4.0, max=4.0, update=_mark_dirty)
    finish_saturation: FloatProperty(name="Saturation", default=1.0, min=0.0, max=4.0, update=_mark_dirty)
    finish_grain: FloatProperty(name="Grain", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=_mark_dirty)
    finish_grain_brightness: FloatProperty(name="Grain Brightness", default=0.0, min=-1.0, max=1.0, update=_mark_dirty)
    finish_grain_saturation: FloatProperty(name="Grain Saturation", default=1.0, min=0.0, max=1.0, subtype="FACTOR", update=_mark_dirty)
    finish_scanline_strength: FloatProperty(name="Scanline Strength", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=_mark_dirty)
    finish_scanline_size: IntProperty(name="Scanline Size", default=2, min=2, max=32, update=_mark_dirty)
    finish_scanline_axis: EnumProperty(
        name="Scanline Axis", default="Y", update=_mark_dirty,
        items=[("Y", "Horizontal Lines", "Darken alternating horizontal lines"), ("X", "Vertical Lines", "Darken alternating vertical lines")],
    )
    finish_scanline_invert: BoolProperty(name="Invert Scanlines", default=False, update=_mark_dirty)
    finish_vignette_strength: FloatProperty(name="Vignette", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=_mark_dirty)
    finish_vignette_roundness: FloatProperty(name="Vignette Roundness", default=1.0, min=0.1, max=4.0, update=_mark_dirty)
    finish_chromatic_aberration: FloatProperty(name="Chromatic Aberration", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=_mark_dirty)
    finish_mask_type: EnumProperty(name="Finish Mask", default="NONE", items=_FINISH_MASK_TYPES, update=_mark_dirty)
    finish_mask_mix: FloatProperty(name="Finish Mask Mix", default=1.0, min=0.0, max=1.0, subtype="FACTOR", update=_mark_dirty)
    finish_mask_invert: BoolProperty(name="Invert Finish Mask", default=False, update=_mark_dirty)
    finish_channel_mask: EnumProperty(name="Finish Channels", default="RGB", items=_CHANNEL_MASKS, update=_mark_dirty)

    # -- add-on state --------------------------------------------------------
    style_preset: EnumProperty(
        name="Style Recipe",
        default="MODERN_INDIE_24",
        items=PRESET_ITEMS,
        description="Choose an editable starting recipe; use Load Style Recipe to apply it",
    )
    random_seed: IntProperty(
        name="Random Seed", default=0, update=_mark_dirty,
        description="Seed for white noise and palette initialization ($randomseed)",
    )
    live_preview: BoolProperty(
        name="Live Preview", default=False, update=_mark_dirty,
        description="Recompute a capped-resolution preview while tweaking",
    )
    preview_mode: EnumProperty(
        name="Live Preview Mode", default="FINAL", update=_mark_dirty,
        description="Draft bypasses intensive dither and quantization stages; Apply always uses final settings",
        items=[
            ("DRAFT", "Draft (Pixelation Only)", "Fast pixelation-only preview while adjusting composition"),
            ("FINAL", "Final Effects", "Preview all enabled effects at the preview resolution"),
        ],
    )
    preview_max_size: IntProperty(
        name="Preview Max Size", default=512, min=64, max=1024, update=_mark_dirty,
        description="Longest-side cap for the live preview",
    )
    # Written by the preview timer, shown in the panel; not user settings.
    preview_status: StringProperty(
        name="Preview Status", default="", options={"HIDDEN"},
        description="Why the live preview is approximate or out of date",
    )
    preview_failed: BoolProperty(name="Preview Failed", default=False, options={"HIDDEN"})
    preview_cache_enabled: BoolProperty(
        name="Cache Live Preview", default=True, update=_mark_dirty,
        description="Reuse identical preview results without starting a worker thread",
    )
    # Explicit v3 scene snapshot.  Image pins remain PointerProperties and are
    # intentionally not serialized into this string.
    v3_plan_json: StringProperty(
        name="V3 Plan Snapshot", default="", options={"HIDDEN"},
        description="Validated JSON snapshot of scalar settings and stage order",
    )
    v3_plan_fingerprint: StringProperty(
        name="V3 Plan Fingerprint", default="", options={"HIDDEN"},
    )
    auto_bake_render: BoolProperty(
        name="Auto Bake Finished Renders", default=False,
        description="Run the exact PixelatorPlus pipeline after each render and update the compositor output node",
    )
    auto_connect_baked_output: BoolProperty(
        name="Auto Connect Baked Output", default=False,
        description="When auto baking, replace the Composite image link with the exact baked output",
    )
    last_output_name: StringProperty(name="Last Output", default="")
    last_palette_name: StringProperty(name="Last Palette Output", default="")
    last_palette_index_name: StringProperty(name="Last Palette Index Output", default="")
    last_lut_name: StringProperty(name="Last LUT Output", default="")


# Settings that describe the workflow or UI state rather than the look.
# Every other non-pin setting is an *effect* setting: it is captured by plan
# snapshots and reset by style recipes (see presets.EFFECT_BASELINE).  New
# workflow settings belong here or under a workflow prefix.
_WORKFLOW_SETTINGS = frozenset({
    "style_preset", "live_preview", "preview_mode", "preview_max_size",
    "preview_cache_enabled", "preview_status", "preview_failed",
    "v3_plan_json", "v3_plan_fingerprint", "auto_bake_render",
    "auto_connect_baked_output",
})
_WORKFLOW_PREFIXES = ("sheet_", "last_")


def _effect_setting_names():
    """Effect settings in declaration order; image pins are excluded."""
    return tuple(
        name for name, prop in PixelatorPlusSettings.__annotations__.items()
        if getattr(prop, "function", None) is not PointerProperty
        and name not in _WORKFLOW_SETTINGS
        and not name.startswith(_WORKFLOW_PREFIXES)
    )


EFFECT_SETTINGS = _effect_setting_names()


def ensure_v3_stages(settings):
    """Complete the canonical v3 stage stack and return it.

    Adds any stage missing from the collection (a new scene, or a file saved
    before a stage existed), keeps the dependency order, and re-enables the
    mandatory Pixelate stage.  It only writes when something is wrong, so
    calling it on a complete stack does not fire update hooks or invalidate
    the live preview.  This mutates scene data: call it from operators, never
    from ``Panel.draw`` or parameter collection.
    """
    stack = settings.v3.stage_stack
    present = {item.stage_id for item in stack}
    for stage_id, _label, _description in V3_STAGE_ITEMS:
        if stage_id not in present:
            item = stack.add()
            item.stage_id = stage_id
    # Appended stages must still follow the dependency order the plan
    # validator enforces.
    for target, (stage_id, _label, _description) in enumerate(V3_STAGE_ITEMS):
        current = next(i for i, item in enumerate(stack) if item.stage_id == stage_id)
        if current != target:
            stack.move(current, target)
    for item in stack:
        # The grid is the required input for every v3 stage.
        if item.stage_id == "pixelate" and not item.enabled:
            item.enabled = True
    return stack


def collect_snapshot_params(settings):
    """Copy raw scalar settings for a lossless v3 plan snapshot.

    Unlike :func:`collect_params`, this does not replace inactive execution
    controls with ``None``.  Snapshot restore must be able to write every
    stored value back to its Blender property even while its matching option
    is disabled.
    """
    params = {}
    for name in EFFECT_SETTINGS:
        value = getattr(settings, name)
        if hasattr(value, "__len__") and not isinstance(value, str):
            value = tuple(value)  # vector properties (colors, tile sizes)
        params[name] = value
    # Parameter collection runs from preview and Apply paths.  It must report
    # an existing stage policy without initializing the collection or forcing
    # a disabled flag back on; operators and presets explicitly initialize
    # the stack when that mutation is wanted.
    stack = settings.v3.stage_stack
    params["v3_stage_order"] = tuple(item.stage_id for item in stack)
    params["v3_stage_enabled"] = {item.stage_id: bool(item.enabled) for item in stack}
    params["v3_palette_lock"] = settings.v3.palette_lock
    params["v3_palette_lock_strength"] = settings.v3.palette_lock_strength
    params["v3_grid_coherence"] = settings.v3.grid_coherence
    return params


def collect_params(settings):
    """Derive the plain execution dictionary consumed by core.pipeline."""
    params = collect_snapshot_params(settings)
    # mask shaping extras (build_mask kwargs)
    params["mask_lum_range"] = (settings.dither_mask_lum_low, settings.dither_mask_lum_high)
    params["mask_sat_range"] = (settings.dither_mask_sat_low, settings.dither_mask_sat_high)
    params["mask_gradient_angle"] = settings.dither_mask_gradient_angle
    params["mask_invert"] = settings.dither_mask_invert
    params["mask_blur"] = settings.dither_mask_blur
    params["quantize_seed"] = (
        settings.quantize_seed if settings.use_explicit_quantize_seed else None
    )
    params["chroma_importance"] = (
        settings.chroma_importance if settings.use_chroma_importance else None
    )
    # Blender stores FILE_PATH values relative to the .blend ("//...") by
    # default; the core opens plain filesystem paths.
    if settings.cube_lut_path:
        params["cube_lut_path"] = bpy.path.abspath(settings.cube_lut_path)
    return params


def register():
    bpy.utils.register_class(PixelatorPlusV3Stage)
    bpy.utils.register_class(PixelatorPlusV3Settings)
    bpy.utils.register_class(PixelatorPlusSettings)
    bpy.types.Scene.pixelatorplus = PointerProperty(type=PixelatorPlusSettings)


def unregister():
    del bpy.types.Scene.pixelatorplus
    bpy.utils.unregister_class(PixelatorPlusSettings)
    bpy.utils.unregister_class(PixelatorPlusV3Settings)
    bpy.utils.unregister_class(PixelatorPlusV3Stage)
