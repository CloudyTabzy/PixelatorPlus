"""The Dither section: patterns, strategies, masks, and frequency weights.

Mixin for ``properties.PixelatorPlusSettings``; Blender registers the
annotations of mixin bases, so these are ordinary scene settings.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    IntVectorProperty,
    PointerProperty,
)

from .common import mark_dirty
from .items import (
    DITHER_TYPES,
    BLEND_MODES,
    DITHER_STRATEGIES,
    MASK_TYPES,
)


class DitherSettings:
    custom_dither_image: PointerProperty(
        name="Custom Dither Pattern", type=bpy.types.Image, update=mark_dirty,
        description="Custom dither pattern (any square resolution)",
    )
    custom_mask_image: PointerProperty(
        name="Custom Dither Mask", type=bpy.types.Image, update=mark_dirty,
        description="Custom dither mask texture",
    )
    threshold_map_image: PointerProperty(
        name="Threshold Map", type=bpy.types.Image, update=mark_dirty,
        description="Optional image modulating palette-threshold dither",
    )
    # Dithering
    dither_type: EnumProperty(
        name="Dither Type", default="NONE", items=DITHER_TYPES, update=mark_dirty,
    )
    dither_strategy: EnumProperty(
        name="Dither Strategy", default="OVERLAY", items=DITHER_STRATEGIES,
        update=mark_dirty,
        description="Use a texture overlay or palette-aware threshold selection",
    )
    custom_dither_resolution: IntVectorProperty(
        name="Custom Dither Resolution", size=2, default=(8, 8), min=0, max=10,
        update=mark_dirty,
        description="Custom dither tile size as a power of two per axis (8 = 256 px)",
    )
    dither_blend_mode: EnumProperty(
        name="Blend Mode", default="SOFT_LIGHT", items=BLEND_MODES, update=mark_dirty,
    )
    use_gray_dither: BoolProperty(
        name="Grayscale Dither", default=False, update=mark_dirty,
        description="Use the pattern's red channel as a grayscale dither",
    )
    dither_strength: FloatProperty(
        name="Blend Strength", default=0.25, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
    )
    dither_saturation: FloatProperty(
        name="Blend Saturation", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
    )
    palette_dither_contrast: FloatProperty(
        name="Palette Dither Contrast", default=1.0, min=0.0, max=4.0,
        update=mark_dirty,
        description="Expand or compress the palette-boundary threshold response",
    )
    palette_dither_invert: BoolProperty(
        name="Invert Palette Threshold", default=False, update=mark_dirty,
    )
    lock_dither_to_grid: BoolProperty(
        name="Lock Dither to Pixel Grid", default=False, update=mark_dirty,
        description="Generate one dither threshold per pixel-grid cell before nearest upscaling",
    )
    dither_mask_type: EnumProperty(
        name="Dither Mask Type", default="NONE", items=MASK_TYPES, update=mark_dirty,
    )
    dither_cutoff: FloatProperty(
        name="Dither Mask Strength", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
    )
    dither_mask_gamma: FloatProperty(
        name="Dither Mask Gamma", default=1.0, min=0.1, max=4.0, update=mark_dirty,
    )
    preview_dither_mask: BoolProperty(
        name="Preview Dither Mask", default=False, update=mark_dirty,
        description="Output the dither mask instead of the image",
    )
    # mask shaping extras (not from the Substance spec)
    dither_mask_lum_low: FloatProperty(
        name="Luminance Low", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty, description="Lower edge of the luminance band mask",
    )
    dither_mask_lum_high: FloatProperty(
        name="Luminance High", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty, description="Upper edge of the luminance band mask",
    )
    dither_mask_sat_low: FloatProperty(
        name="Saturation Low", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty, description="Lower edge of the saturation band mask",
    )
    dither_mask_sat_high: FloatProperty(
        name="Saturation High", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty, description="Upper edge of the saturation band mask",
    )
    dither_mask_gradient_angle: FloatProperty(
        name="Gradient Angle", default=0.0, min=0.0, max=360.0, update=mark_dirty,
        description="Direction of the gradient ramp mask in degrees (0 = left to right, 90 = top to bottom)",
    )
    dither_mask_invert: BoolProperty(
        name="Invert Mask", default=False, update=mark_dirty,
        description="Invert the final dither mask",
    )
    dither_mask_blur: IntProperty(
        name="Blur Mask", default=0, min=0, max=64, update=mark_dirty,
        description="Soften the final dither mask by this many pixels (0 = off)",
    )
    show_mask_controls: BoolProperty(
        name="Frequency Weights", default=False, update=mark_dirty,
        description="Show per-frequency weights for the edge and flat masks",
    )
    huge: FloatProperty(name="Huge", default=1.0, min=0.0, max=1.0, update=mark_dirty)
    big: FloatProperty(name="Big", default=1.0, min=0.0, max=1.0, update=mark_dirty)
    large: FloatProperty(name="Large", default=0.8, min=0.0, max=1.0, update=mark_dirty)
    medium: FloatProperty(name="Medium", default=0.6, min=0.0, max=1.0, update=mark_dirty)
    fine: FloatProperty(name="Fine", default=0.4, min=0.0, max=1.0, update=mark_dirty)
    sharp: FloatProperty(name="Sharp", default=0.2, min=0.0, max=1.0, update=mark_dirty)
    pixel_perfect: FloatProperty(
        name="Pixel Perfect", default=0.2, min=0.0, max=1.0, update=mark_dirty,
    )
