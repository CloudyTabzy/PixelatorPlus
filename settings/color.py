"""The Color section: quantization, palettes, LUTs, diffusion, and posterize.

Mixin for ``properties.PixelatorPlusSettings``; Blender registers the
annotations of mixin bases, so these are ordinary scene settings.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from .common import BLEND_RELATIVE_PATH_OPTIONS, mark_dirty
from .items import (
    QUANTIZE_TYPES,
    INIT_MODES,
    COLOR_MODES,
    APPLY_MODES,
    FORCE_COLORS,
    LUTS,
    PALETTE_EXTRACT_METHODS,
    PALETTE_SORT_MODES,
    CHANNEL_MASKS,
    POSTERIZE_RANGE_MODES,
    ALPHA_POLICIES,
)


class ColorSettings:
    custom_lut_image: PointerProperty(
        name="Custom LUT", type=bpy.types.Image, update=mark_dirty,
        description="Custom 4096x4096 LUT image",
    )
    custom_palette_image: PointerProperty(
        name="Custom Palette", type=bpy.types.Image, update=mark_dirty,
        description="Custom palette image (opaque unique colors only; maximum 256)",
    )
    range_map_image: PointerProperty(
        name="Range Map", type=bpy.types.Image, update=mark_dirty,
        description="Optional image controlling local Posterize/Levels amount",
    )
    # Quantization
    quantize_type: EnumProperty(
        name="Quantization Type", default="NONE", items=QUANTIZE_TYPES,
        update=mark_dirty,
    )
    posterize_enabled: BoolProperty(
        name="Enable Posterize / Levels", default=False, update=mark_dirty,
        description="Quantize each channel to explicit display levels before dithering",
    )
    posterize_levels: IntProperty(
        name="Levels per Channel", default=8, min=2, max=256, update=mark_dirty,
        description="Number of output steps per RGB channel",
    )
    posterize_range_mode: EnumProperty(
        name="Level Range", default="FULL", items=POSTERIZE_RANGE_MODES,
        update=mark_dirty,
    )
    posterize_range_low: FloatProperty(
        name="Input Black", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
    )
    posterize_range_high: FloatProperty(
        name="Input White", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
    )
    posterize_percentile_low: FloatProperty(
        name="Shadow Percentile", default=2.0, min=0.0, max=49.0,
        update=mark_dirty,
    )
    posterize_percentile_high: FloatProperty(
        name="Highlight Percentile", default=98.0, min=51.0, max=100.0,
        update=mark_dirty,
    )
    posterize_gamma: FloatProperty(
        name="Posterize Gamma", default=1.0, min=0.1, max=4.0, update=mark_dirty,
        description="Move level thresholds while retaining input endpoints",
    )
    posterize_mix: FloatProperty(
        name="Posterize Mix", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
    )
    posterize_channel_mask: EnumProperty(
        name="Posterize Channels", default="RGB", items=CHANNEL_MASKS, update=mark_dirty,
    )
    posterize_alpha_policy: EnumProperty(
        name="Posterize Alpha", default="PRESERVE", items=ALPHA_POLICIES, update=mark_dirty,
    )
    # error diffusion is an add-on extra (not from the Substance spec)
    diffusion: EnumProperty(
        name="Error Diffusion", default="NONE", update=mark_dirty,
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
        update=mark_dirty,
        description="How much quantization error propagates to neighbors",
    )
    diffusion_serpentine: BoolProperty(
        name="Serpentine Scan", default=True, update=mark_dirty,
        description="Alternate scan direction on each row to reduce directional bias",
    )
    initialize_mode: EnumProperty(
        name="Initialization Mode", default="1", items=INIT_MODES, update=mark_dirty,
        description="Palette initial-color strategy",
    )
    color_mode: EnumProperty(
        name="Build Space", default="RGB", items=COLOR_MODES,
        update=mark_dirty,
        description="Color space in which the palette is generated",
    )
    apply_palette_mode: EnumProperty(
        name="Match Space", default="RGB", items=APPLY_MODES,
        update=mark_dirty,
        description="Color space used to match each pixel to its nearest palette color",
    )
    quantize_quality: IntProperty(
        name="Quality", default=2, min=0, max=8, update=mark_dirty,
        description="Palette-generation quality (sample count and iterations)",
    )
    quantize_seed: FloatProperty(
        name="Initial Random Seed", default=1.0, min=0.0, max=10.0, update=mark_dirty,
        description="Explicit palette-generation seed; uses Random Seed when disabled",
    )
    use_explicit_quantize_seed: BoolProperty(
        name="Use Explicit Palette Seed", default=False, update=mark_dirty,
        description="Use Initial Random Seed instead of the shared Random Seed",
    )
    chroma_importance: FloatProperty(
        name="Color Importance", default=35.0, min=0.0, max=50.0, update=mark_dirty,
        description="Palette chroma weighting reconstruction; neutral when disabled",
    )
    use_chroma_importance: BoolProperty(
        name="Use Color Importance", default=False, update=mark_dirty,
        description="Enable the Color Importance palette weighting control",
    )
    use_pixelated_for_quantize: BoolProperty(
        name="Sample Pixel Grid", default=False, update=mark_dirty,
        description="Build the palette from the downscaled pixel grid instead of the full image",
    )
    palette_extract_method: EnumProperty(
        name="Palette Extraction", default="KMEANS", items=PALETTE_EXTRACT_METHODS,
        update=mark_dirty,
        description="How generated palettes are extracted from the image",
    )
    palette_ramp_count: IntProperty(
        name="Ramps", default=4, min=1, max=32, update=mark_dirty,
        description="Hue families in a Color Ramps palette",
    )
    palette_ramp_steps: IntProperty(
        name="Shades per Ramp", default=4, min=2, max=8, update=mark_dirty,
        description="Dark-to-light shades in each ramp",
    )
    palette_ramp_hue_shift: FloatProperty(
        name="Hue Shift", default=20.0, min=0.0, max=60.0, update=mark_dirty,
        description="Degrees shadows shift toward cool and highlights toward warm",
    )
    palette_sort_mode: EnumProperty(
        name="Palette Sort", default="NONE", items=PALETTE_SORT_MODES,
        update=mark_dirty,
    )
    palette_shift: IntProperty(
        name="Palette Shift", default=0, min=-256, max=256, update=mark_dirty,
        description="Cyclically rotate palette entries after extraction",
    )
    palette_trim: BoolProperty(
        name="Trim Duplicate Colors", default=False, update=mark_dirty,
        description="Remove near-duplicate entries after palette extraction",
    )
    palette_replace_image: PointerProperty(
        name="Replacement Palette", type=bpy.types.Image, update=mark_dirty,
        description="Optional palette image used to replace nearby extracted colors",
    )
    palette_replace_threshold: FloatProperty(
        name="Replacement Threshold", default=0.1, min=0.0, max=1.0,
        subtype="FACTOR", update=mark_dirty,
    )
    k_num_colors: IntProperty(
        name="Number of Colors", default=32, min=2, max=256, update=mark_dirty,
    )
    gamma: FloatProperty(
        name="Palette Gamma", default=1.0, min=0.1, max=4.0,
        update=mark_dirty,
        description="Gamma applied before palette generation; raise it to preserve dark tones",
    )
    force_colors: EnumProperty(
        name="Force Colors", default="NONE", items=FORCE_COLORS, update=mark_dirty,
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
        name="Use Range Adaptive Mode", default=False, update=mark_dirty,
    )
    quantize_colors_or_bits: EnumProperty(
        name="Color Mode", default="COLORS", update=mark_dirty,
        items=[
            ("COLORS", "Colors Per Channel", "Exact level count per channel"),
            ("BITS", "Bits Per Channel", "Bit depth per channel"),
        ],
    )
    quantize_colors: IntProperty(
        name="Colors Per Channel", default=256, min=2, max=256, update=mark_dirty,
    )
    quantize_bits: IntProperty(
        name="Bits Per Channel", default=8, min=1, max=8, update=mark_dirty,
    )
    output_default_lut: BoolProperty(
        name="Output Identity LUT", default=False,
        description="Also produce the identity 4096x4096 LUT on Apply",
    )
    lut: EnumProperty(
        name="LUT", default="AMIGA", items=LUTS, update=mark_dirty,
    )
    cube_lut_path: StringProperty(
        name=".cube LUT File", default="", subtype="FILE_PATH", update=mark_dirty,
        options=BLEND_RELATIVE_PATH_OPTIONS,
        description="Path to a portable 3D .cube LUT",
    )
    cube_lut_interpolation: EnumProperty(
        name=".cube Interpolation", default="TRILINEAR", update=mark_dirty,
        items=[
            ("TRILINEAR", "Trilinear", "Smooth interpolation through the 3D LUT"),
            ("NEAREST", "Nearest", "Nearest lattice point for hard stepped looks"),
        ],
    )
    cube_lut_strength: FloatProperty(
        name=".cube Strength", default=1.0, min=0.0, max=1.0,
        subtype="FACTOR", update=mark_dirty,
    )
