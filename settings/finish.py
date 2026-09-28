"""The Finish section: display finishing and the shared strength map.

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
)

from .common import mark_dirty
from .items import (
    FINISH_MASK_TYPES,
    CHANNEL_MASKS,
)


class FinishSettings:
    # Named v3 maps keep the advanced workflow expressive without adding an
    # image socket to every scalar control.
    strength_map_image: PointerProperty(
        name="Strength Map", type=bpy.types.Image, update=mark_dirty,
        description="Optional image controlling dither, finish, and stage strength",
    )
    # Display finishing
    finish_enabled: BoolProperty(
        name="Enable Display Finish", default=False, update=mark_dirty,
        description="Apply the post-quantization display finishing stack",
    )
    finish_brightness: FloatProperty(name="Brightness", default=0.0, min=-1.0, max=1.0, update=mark_dirty)
    finish_contrast: FloatProperty(name="Contrast", default=1.0, min=0.0, max=4.0, update=mark_dirty)
    finish_exposure: FloatProperty(name="Exposure", default=0.0, min=-4.0, max=4.0, update=mark_dirty)
    finish_saturation: FloatProperty(name="Saturation", default=1.0, min=0.0, max=4.0, update=mark_dirty)
    finish_grain: FloatProperty(name="Grain", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=mark_dirty)
    finish_grain_brightness: FloatProperty(name="Grain Brightness", default=0.0, min=-1.0, max=1.0, update=mark_dirty)
    finish_grain_saturation: FloatProperty(name="Grain Saturation", default=1.0, min=0.0, max=1.0, subtype="FACTOR", update=mark_dirty)
    finish_scanline_strength: FloatProperty(name="Scanline Strength", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=mark_dirty)
    finish_scanline_size: IntProperty(name="Scanline Size", default=2, min=2, max=32, update=mark_dirty)
    finish_scanline_axis: EnumProperty(
        name="Scanline Axis", default="Y", update=mark_dirty,
        items=[("Y", "Horizontal Lines", "Darken alternating horizontal lines"), ("X", "Vertical Lines", "Darken alternating vertical lines")],
    )
    finish_scanline_invert: BoolProperty(name="Invert Scanlines", default=False, update=mark_dirty)
    finish_vignette_strength: FloatProperty(name="Vignette", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=mark_dirty)
    finish_vignette_roundness: FloatProperty(name="Vignette Roundness", default=1.0, min=0.1, max=4.0, update=mark_dirty)
    finish_chromatic_aberration: FloatProperty(name="Chromatic Aberration", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=mark_dirty)
    finish_mask_type: EnumProperty(name="Finish Mask", default="NONE", items=FINISH_MASK_TYPES, update=mark_dirty)
    finish_mask_mix: FloatProperty(name="Finish Mask Mix", default=1.0, min=0.0, max=1.0, subtype="FACTOR", update=mark_dirty)
    finish_mask_invert: BoolProperty(name="Invert Finish Mask", default=False, update=mark_dirty)
    finish_channel_mask: EnumProperty(name="Finish Channels", default="RGB", items=CHANNEL_MASKS, update=mark_dirty)
