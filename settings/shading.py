"""The Tone Bands section: cel-style banded lighting and its scene maps.

Mixin for ``properties.PixelatorPlusSettings``; Blender registers the
annotations of mixin bases, so these are ordinary scene settings.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
)

from .common import mark_dirty


class ShadingSettings:
    shade_bands: BoolProperty(
        name="Tone Bands", default=False, update=mark_dirty,
        description="Shade with a few flat tones instead of smooth gradients (cel look)",
    )
    shade_band_count: IntProperty(
        name="Bands", default=3, min=2, max=8, update=mark_dirty,
        description="Number of flat tones per region",
    )
    shade_band_source: EnumProperty(
        name="Band By", default="LIGHTNESS", update=mark_dirty,
        items=[
            ("LIGHTNESS", "Image Lightness", "Band by the image's own lightness"),
            ("LIGHT_MAP", "Light Map", "Band by a rendered, texture-free light map so "
             "dark texture is not read as shadow"),
        ],
    )
    shade_band_per_part: BoolProperty(
        name="Per Part", default=False, update=mark_dirty,
        description="Give every part (from the ID map) its own full set of bands",
    )
    shade_flatten: BoolProperty(
        name="Flatten Color", default=True, update=mark_dirty,
        description="Give each band one flat color (cel look); off keeps each pixel's hue",
    )
    light_map_image: PointerProperty(
        name="Light Map", type=bpy.types.Image, update=mark_dirty,
        description="Texture-free lighting render with the same framing as the input "
        "(Render Light Map creates one; sprite sheets render their own)",
    )
